#!/usr/bin/env python3
"""
Live "extra flips" scan for the current epoch (before validation).

Goal:
- Count how many identities (authors) have published more than N flips (default N=3)
- Compute total extra flips beyond N (sum(max(0, count - N)))
- Optional: fetch stake information:
  - --fetch-stake: fetch stake only for authors with extra flips (flipCount > threshold)
  - --fetch-stake-all: fetch stake for ALL authors who submitted at least 1 flip (heavy)

Endpoints used (Idena indexer API):
- GET /Epoch/Last
- GET /Epoch/{epoch}/Flips (paged)
- GET /Address/{address} (best-effort) OR /Identity/{address} fallback (best-effort)

No external dependencies (stdlib only).
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import os
import time
from collections import Counter
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


BASE_URL_DEFAULT = "https://api.idena.io/api"
MAX_PAGE_SIZE = 100


def utc_ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def log(msg: str) -> None:
    print(f"[{utc_ts()}] {msg}", flush=True)


def iso_to_unix(iso_value: str) -> Optional[float]:
    try:
        if iso_value.endswith("Z"):
            iso_value = iso_value[:-1] + "+00:00"
        return datetime.fromisoformat(iso_value).timestamp()
    except Exception:
        return None


def unix_to_iso(ts: float) -> str:
    return datetime.utcfromtimestamp(ts).isoformat(timespec="seconds") + "Z"


def load_json_file(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def write_json_file(path: str, data: Dict[str, Any]) -> None:
    if not path:
        return
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)


def normalize_progress_points(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ts = row.get("timestamp")
        if not isinstance(ts, str):
            continue
        normalized.append(
            {
                "timestamp": ts,
                "flipsSeen": int(safe_float(row.get("flipsSeen"))),
                "uniqueAuthors": int(safe_float(row.get("uniqueAuthors"))),
            }
        )
    normalized.sort(key=lambda x: x["timestamp"])
    return normalized


def build_progress_series(history_by_epoch: Dict[str, Any], epoch: int) -> Dict[str, Any]:
    current_points = normalize_progress_points(history_by_epoch.get(str(epoch), []))
    previous_epochs: List[Dict[str, Any]] = []

    for prev_epoch in (epoch - 1, epoch - 2):
        if prev_epoch <= 0:
            continue
        prev_points = normalize_progress_points(history_by_epoch.get(str(prev_epoch), []))
        if prev_points:
            previous_epochs.append({"epoch": prev_epoch, "points": prev_points})

    return {
        "currentEpoch": {"epoch": epoch, "points": current_points},
        "previousEpochs": previous_epochs,
    }


class HttpClient:
    def __init__(self, base_url: str, timeout: int = 25, retries: int = 6, backoff_sec: float = 1.3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff_sec = backoff_sec

    def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        qs = ""
        if params:
            qs = "?" + urlencode(params)
        url = f"{self.base_url}{path}{qs}"

        last_err: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                req = Request(url, headers={"Accept": "application/json", "User-Agent": "idena-extra-flips-live/1.1"})
                with urlopen(req, timeout=self.timeout) as resp:
                    status = getattr(resp, "status", 200)
                    if status == 429:
                        time.sleep(self.backoff_sec * attempt)
                        continue
                    body = resp.read().decode("utf-8", errors="replace")

                js = json.loads(body)
                err = js.get("error")
                if isinstance(err, dict) and err.get("message"):
                    raise RuntimeError(f"API error at {path}: {err.get('message')}")
                return js
            except (HTTPError, URLError, json.JSONDecodeError, RuntimeError) as e:
                last_err = e
                time.sleep(self.backoff_sec * attempt)

        raise RuntimeError(f"GET failed after {self.retries} retries: {url} ({last_err})")


def extract_epoch_and_validation_time(res: Any) -> Tuple[int, Optional[str]]:
    epoch = 0
    validation_time: Optional[str] = None

    if isinstance(res, int):
        epoch = res
    elif isinstance(res, dict):
        for k in ("epoch", "Epoch", "number", "Number"):
            v = res.get(k)
            if isinstance(v, int):
                epoch = v
                break
        vt = res.get("validationTime")
        if isinstance(vt, str):
            validation_time = vt

    return epoch, validation_time


def get_current_epoch_info(api: HttpClient) -> Tuple[int, Optional[str]]:
    js = api.get_json("/Epoch/Last")
    res = js.get("result")
    epoch, validation_time = extract_epoch_and_validation_time(res)
    if epoch > 0:
        return epoch, validation_time
    raise RuntimeError(f"Unexpected /Epoch/Last result: {res}")


def get_epoch_validation_time(api: HttpClient, epoch: int) -> Optional[str]:
    js = api.get_json(f"/Epoch/{epoch}")
    res = js.get("result")
    _, validation_time = extract_epoch_and_validation_time(res)
    return validation_time


def paged_flips(api: HttpClient, epoch: int, page_size: int, sleep_per_page: float) -> Iterable[Dict[str, Any]]:
    token: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"limit": page_size}
        if token:
            params["continuationToken"] = token

        js = api.get_json(f"/Epoch/{epoch}/Flips", params=params)
        items = js.get("result") or []
        if not isinstance(items, list):
            raise RuntimeError(f"Unexpected result type at /Epoch/{epoch}/Flips: {type(items)}")

        for it in items:
            if isinstance(it, dict):
                yield it

        token = js.get("continuationToken")
        if not token:
            break

        if sleep_per_page > 0:
            time.sleep(sleep_per_page)


def paged_bad_authors(api: HttpClient, epoch: int, page_size: int, sleep_per_page: float) -> Iterable[Dict[str, Any]]:
    token: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"limit": page_size}
        if token:
            params["continuationToken"] = token

        js = api.get_json(f"/Epoch/{epoch}/Authors/Bad", params=params)
        items = js.get("result") or []
        if not isinstance(items, list):
            raise RuntimeError(f"Unexpected result type at /Epoch/{epoch}/Authors/Bad: {type(items)}")

        for it in items:
            if isinstance(it, dict):
                yield it

        token = js.get("continuationToken")
        if not token:
            break

        if sleep_per_page > 0:
            time.sleep(sleep_per_page)


def safe_float(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def try_get_author(flip: Dict[str, Any]) -> str:
    for k in ("author", "authorAddress", "address"):
        a = flip.get(k)
        if isinstance(a, str) and a.startswith("0x") and len(a) == 42:
            return a.lower()
    return ""


def try_get_cid(flip: Dict[str, Any]) -> str:
    c = flip.get("cid") or flip.get("Cid") or ""
    return c if isinstance(c, str) else ""


def try_get_words(flip: Dict[str, Any]) -> Tuple[str, str]:
    words = flip.get("words")
    if not isinstance(words, dict):
        return "", ""

    word1 = words.get("word1")
    word2 = words.get("word2")
    word1_name = ""
    word2_name = ""

    if isinstance(word1, dict):
        name = word1.get("name")
        if isinstance(name, str):
            word1_name = name

    if isinstance(word2, dict):
        name = word2.get("name")
        if isinstance(name, str):
            word2_name = name

    return word1_name, word2_name


def fetch_wrongwords_bad_authors(api: HttpClient, epoch: int, page_size: int, sleep_per_page: float) -> set[str]:
    bad: set[str] = set()
    for row in paged_bad_authors(api, epoch=epoch, page_size=page_size, sleep_per_page=sleep_per_page):
        addr = row.get("address")
        reason = row.get("reason")
        wrong_words_flag = row.get("wrongWords")

        if isinstance(addr, str) and len(addr) == 42 and addr.startswith("0x"):
            if reason == "WrongWords" or wrong_words_flag is True:
                bad.add(addr.lower())
    return bad


def build_grade_identity_leaderboard(
    api: HttpClient,
    epoch: int,
    page_size: int,
    sleep_per_page: float,
    allowed_statuses: List[str],
    include_zero: bool,
    top_n: int,
    top_flips_n: int,
    out_dir: str,
) -> Dict[str, Any]:
    allowed_status = set(allowed_statuses) if allowed_statuses else None

    log(f"Fetching wrongWords bad authors for epoch {epoch} ...")
    bad_authors = fetch_wrongwords_bad_authors(api, epoch=epoch, page_size=page_size, sleep_per_page=sleep_per_page)
    log(f"wrongWords bad authors (epoch {epoch}): {len(bad_authors)}")

    totals: Dict[str, Dict[str, float]] = {}
    flips_seen = 0
    flips_kept = 0
    flip_heap: List[Tuple[float, str, Dict[str, Any]]] = []
    top_flips_limit = max(0, int(top_flips_n))

    log(f"Building gradeScore identity leaderboard for epoch {epoch} ...")
    for fl in paged_flips(api, epoch=epoch, page_size=page_size, sleep_per_page=sleep_per_page):
        flips_seen += 1
        author = try_get_author(fl)
        if not author or author in bad_authors:
            continue

        status = fl.get("status")
        if allowed_status is not None and status not in allowed_status:
            continue

        grade_score = safe_float(fl.get("gradeScore"))
        if (not include_zero) and grade_score <= 0:
            continue

        flips_kept += 1

        if author not in totals:
            totals[author] = {"total": 0.0, "count": 0.0, "max": 0.0}

        totals[author]["total"] += grade_score
        totals[author]["count"] += 1.0
        if grade_score > totals[author]["max"]:
            totals[author]["max"] = grade_score

        if flips_seen % 2000 == 0:
            log(f"grade leaderboard progress: seen={flips_seen} kept={flips_kept}")

        cid = try_get_cid(fl)
        if top_flips_limit > 0 and cid:
            word1, word2 = try_get_words(fl)
            flip_row = {
                "cid": cid,
                "author": author,
                "gradeScore": grade_score,
                "status": status if isinstance(status, str) else "",
                "word1": word1,
                "word2": word2,
            }
            heap_item = (grade_score, cid, flip_row)
            if len(flip_heap) < top_flips_limit:
                heapq.heappush(flip_heap, heap_item)
            else:
                if (grade_score, cid) > (flip_heap[0][0], flip_heap[0][1]):
                    heapq.heapreplace(flip_heap, heap_item)

    identities = []
    for addr, agg in totals.items():
        count = int(agg["count"])
        total = float(agg["total"])
        max_score = float(agg["max"])
        avg = (total / count) if count else 0.0
        identities.append(
            {
                "address": addr,
                "totalGradeScore": total,
                "flipCount": count,
                "avgGradeScore": avg,
                "maxFlipGradeScore": max_score,
            }
        )

    identities_sorted = sorted(
        identities,
        key=lambda x: (x["totalGradeScore"], x["flipCount"], x["address"]),
        reverse=True,
    )

    csv_path = os.path.join(out_dir, f"grade_identity_leaderboard_epoch{epoch}.csv")
    csv_rows: List[List[Any]] = []
    for i, row in enumerate(identities_sorted, start=1):
        csv_rows.append(
            [
                i,
                f"{row['totalGradeScore']:.8f}",
                row["flipCount"],
                f"{row['avgGradeScore']:.8f}",
                f"{row['maxFlipGradeScore']:.8f}",
                row["address"],
                f"https://scan.idena.io/address/{row['address']}",
            ]
        )

    write_csv(
        csv_path,
        header=[
            "rank",
            "totalGradeScore",
            "flipCount",
            "avgGradeScore",
            "maxFlipGradeScore",
            "address",
            "scan_url",
        ],
        rows=csv_rows,
    )

    top_rows = identities_sorted[: max(0, top_n)]
    top_identities: List[Dict[str, Any]] = []
    identity_lookup: List[Dict[str, Any]] = []
    rank_by_address: Dict[str, int] = {}
    for i, row in enumerate(identities_sorted, start=1):
        rank_by_address[row["address"]] = i
        identity_lookup.append(
            {
                "rank": i,
                "address": row["address"],
                "totalGradeScore": row["totalGradeScore"],
                "flipCount": row["flipCount"],
                "avgGradeScore": row["avgGradeScore"],
                "maxFlipGradeScore": row["maxFlipGradeScore"],
                "scanUrl": f"https://scan.idena.io/address/{row['address']}",
            }
        )

    for i, row in enumerate(top_rows, start=1):
        top_identities.append(
            {
                "rank": i,
                "address": row["address"],
                "totalGradeScore": row["totalGradeScore"],
                "flipCount": row["flipCount"],
                "avgGradeScore": row["avgGradeScore"],
                "maxFlipGradeScore": row["maxFlipGradeScore"],
                "scanUrl": f"https://scan.idena.io/address/{row['address']}",
            }
        )

    top_flips_sorted = sorted(
        [item[2] for item in flip_heap],
        key=lambda x: (x["gradeScore"], x["cid"]),
        reverse=True,
    )
    top_flips: List[Dict[str, Any]] = []
    for i, row in enumerate(top_flips_sorted, start=1):
        author_rank = rank_by_address.get(row["author"])
        top_flips.append(
            {
                "rank": i,
                "cid": row["cid"],
                "author": row["author"],
                "authorRank": author_rank,
                "gradeScore": row["gradeScore"],
                "status": row["status"],
                "word1": row["word1"],
                "word2": row["word2"],
                "scanUrl": f"https://scan.idena.io/flip/{row['cid']}",
                "authorScanUrl": f"https://scan.idena.io/address/{row['author']}",
            }
        )

    return {
        "enabled": True,
        "epoch": epoch,
        "topLimit": max(0, int(top_n)),
        "topFlipsLimit": top_flips_limit,
        "excludedWrongWordsAuthorsCount": len(bad_authors),
        "filters": {
            "includeZero": bool(include_zero),
            "status": sorted(list(allowed_status)) if allowed_status is not None else None,
        },
        "counts": {
            "flipsSeen": flips_seen,
            "flipsKept": flips_kept,
            "uniqueAuthors": len(identities_sorted),
        },
        "topIdentities": top_identities,
        "identityLookup": identity_lookup,
        "topFlips": top_flips,
        "identityLeaderboardCsvPath": csv_path,
    }


def extract_stake_from_result(res: Any) -> Tuple[float, str]:
    """
    Try multiple known-ish shapes. Returns (stake, note).
    """
    if not isinstance(res, dict):
        return 0.0, "result_not_dict"

    # common top-level keys
    for k in ("stake", "Stake", "stakeBalance", "stakeAmount"):
        if k in res:
            return safe_float(res.get(k)), ""

    # nested balance object
    bal = res.get("balance")
    if isinstance(bal, dict):
        for k in ("stake", "Stake"):
            if k in bal:
                return safe_float(bal.get(k)), ""

    # nested profile/state object
    for k in ("profile", "state"):
        obj = res.get(k)
        if isinstance(obj, dict):
            for kk in ("stake", "Stake"):
                if kk in obj:
                    return safe_float(obj.get(kk)), ""

    return 0.0, "stake_not_found"


def fetch_stake_for_address_best_effort(api: HttpClient, address: str) -> Tuple[float, str]:
    """
    Best-effort stake fetch with fallback endpoints.
    Returns (stake, note).
    """
    # Try /Address/{addr}
    try:
        js = api.get_json(f"/Address/{address}")
        stake, note = extract_stake_from_result(js.get("result"))
        if stake > 0 or note != "stake_not_found":
            return stake, note
    except Exception as e:
        # keep going, try fallback
        pass

    # Try /Identity/{addr} as fallback
    try:
        js = api.get_json(f"/Identity/{address}")
        stake, note = extract_stake_from_result(js.get("result"))
        return stake, note
    except Exception as e:
        return 0.0, f"stake_fetch_error:{e}"


def write_csv(path: str, header: List[str], rows: List[List[Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Live count of identities with >N published flips in the current epoch.")
    ap.add_argument("--base-url", default=BASE_URL_DEFAULT, help="Idena API base URL (default: https://api.idena.io/api)")
    ap.add_argument("--epoch", type=int, default=0, help="Epoch number. If 0, uses current epoch from /Epoch/Last.")
    ap.add_argument("--threshold", type=int, default=3, help="Count identities with flipCount > threshold (default: 3).")
    ap.add_argument("--page-size", type=int, default=100, help="Pagination page size (limit=). Max is 100.")
    ap.add_argument("--sleep-per-page", type=float, default=0.1, help="Delay between list pages (sec).")
    ap.add_argument("--top", type=int, default=50, help="Print top N authors by flipCount to console.")
    ap.add_argument("--out-dir", default="./out", help="Output directory.")
    ap.add_argument("--fetch-stake", action="store_true", help="Fetch stake for authors with extra flips (flipCount > threshold).")
    ap.add_argument("--fetch-stake-all", action="store_true", help="Fetch stake for ALL authors who submitted flips (heavy).")
    ap.add_argument("--stake-sleep", type=float, default=0.10, help="Sleep between stake calls (sec). Helps avoid rate limits.")
    ap.add_argument("--grade-top", type=int, default=10, help="Top N identities by total gradeScore to return in meta (default: 10).")
    ap.add_argument("--grade-epoch-offset", type=int, default=1, help="Use (live epoch - offset) for grade leaderboard epoch (default: 1).")
    ap.add_argument("--grade-status", action="append", default=[], help="Repeatable status filter for grade leaderboard.")
    ap.add_argument("--grade-include-zero", action="store_true", help="Include flips with gradeScore <= 0 in grade leaderboard.")
    ap.add_argument("--grade-top-flips", type=int, default=10, help="Top N flips by gradeScore for last epoch (default: 10).")
    ap.add_argument("--cache-file", default="./cache/live_scan_state.json", help="Local JSON state cache for rate-limit and graph history.")
    ap.add_argument("--min-refresh-seconds", type=int, default=30, help="Minimum seconds between external API refreshes (default: 30).")
    ap.add_argument("--disable-cache", action="store_true", help="Disable local cache/rate-limit storage.")
    ap.add_argument("--disable-grade-leaderboard", action="store_true", help="Disable grade leaderboard generation.")
    args = ap.parse_args()

    if args.page_size < 1 or args.page_size > MAX_PAGE_SIZE:
        raise SystemExit(f"--page-size must be 1..{MAX_PAGE_SIZE}")

    thr = int(args.threshold)
    grade_statuses = list(args.grade_status) if args.grade_status else ["Qualified", "WeaklyQualified"]

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    cache_key_obj = {
        "baseUrl": args.base_url,
        "epoch": int(args.epoch),
        "threshold": thr,
        "pageSize": int(args.page_size),
        "gradeEpochOffset": int(args.grade_epoch_offset),
        "gradeStatus": sorted(grade_statuses),
        "gradeIncludeZero": bool(args.grade_include_zero),
        "gradeTop": int(args.grade_top),
        "gradeTopFlips": int(args.grade_top_flips),
        "disableGradeLeaderboard": bool(args.disable_grade_leaderboard),
    }
    cache_key = json.dumps(cache_key_obj, sort_keys=True)

    state: Dict[str, Any] = {}
    history_by_epoch: Dict[str, Any] = {}
    min_refresh_seconds = max(0, int(args.min_refresh_seconds))

    if not args.disable_cache:
        state = load_json_file(args.cache_file)
        maybe_history = state.get("historyByEpoch")
        if isinstance(maybe_history, dict):
            history_by_epoch = maybe_history

        last_scan = state.get("lastScan")
        if min_refresh_seconds > 0 and isinstance(last_scan, dict):
            if last_scan.get("cacheKey") == cache_key:
                last_fresh_scan_at = last_scan.get("freshTimestamp")
                if isinstance(last_fresh_scan_at, str):
                    last_unix = iso_to_unix(last_fresh_scan_at)
                    if last_unix is not None:
                        age = time.time() - last_unix
                        if age < min_refresh_seconds:
                            last_meta = last_scan.get("meta")
                            if isinstance(last_meta, dict):
                                cached_meta = json.loads(json.dumps(last_meta))
                                remaining = max(0, int(min_refresh_seconds - age))
                                next_refresh_at = unix_to_iso(last_unix + min_refresh_seconds)
                                request_timestamp = utc_ts()

                                cached_epoch = int(safe_float(cached_meta.get("epoch")))
                                cached_threshold = int(safe_float(cached_meta.get("threshold"))) or thr
                                cached_counts = cached_meta.get("counts")
                                if not isinstance(cached_counts, dict):
                                    cached_counts = {}

                                if cached_epoch <= 0:
                                    cached_epoch = int(args.epoch)
                                if cached_epoch > 0:
                                    epoch_key = str(cached_epoch)
                                    epoch_points = normalize_progress_points(history_by_epoch.get(epoch_key, []))
                                    epoch_points.append(
                                        {
                                            "timestamp": request_timestamp,
                                            "flipsSeen": int(safe_float(cached_counts.get("flipsSeen"))),
                                            "uniqueAuthors": int(safe_float(cached_counts.get("uniqueAuthors"))),
                                        }
                                    )
                                    history_by_epoch[epoch_key] = epoch_points[-1500:]
                                    known_epochs = sorted([int(k) for k in history_by_epoch.keys() if str(k).isdigit()], reverse=True)
                                    keep_epochs = set(known_epochs[:6])
                                    for key in list(history_by_epoch.keys()):
                                        if str(key).isdigit() and int(key) not in keep_epochs:
                                            del history_by_epoch[key]

                                progress = cached_meta.get("progress")
                                if not isinstance(progress, dict):
                                    progress = {}
                                progress["cacheUsed"] = True
                                progress["minRefreshSeconds"] = min_refresh_seconds
                                progress["secondsUntilNextRefresh"] = remaining
                                progress["nextRefreshAt"] = next_refresh_at
                                progress["lastFreshScanAt"] = last_fresh_scan_at
                                progress["lastRequestAt"] = request_timestamp
                                progress["historyFile"] = args.cache_file
                                if cached_epoch > 0:
                                    progress["series"] = build_progress_series(history_by_epoch, cached_epoch)
                                cached_meta["progress"] = progress

                                if cached_epoch <= 0:
                                    cached_epoch = int(args.epoch)
                                cached_meta_path = os.path.join(out_dir, f"live_extra_flips_epoch{cached_epoch}_gt{cached_threshold}.meta.json")
                                with open(cached_meta_path, "w", encoding="utf-8") as f:
                                    json.dump(cached_meta, f, indent=2)

                                state["historyByEpoch"] = history_by_epoch
                                state["lastScan"] = {
                                    "cacheKey": cache_key,
                                    "freshTimestamp": last_fresh_scan_at,
                                    "meta": cached_meta,
                                }
                                write_json_file(args.cache_file, state)

                                log(
                                    f"Using cached snapshot from {last_fresh_scan_at} "
                                    f"(next fresh API refresh at {next_refresh_at})"
                                )
                                log(f"Wrote META (cached): {cached_meta_path}")
                                return 0

    api = HttpClient(base_url=args.base_url)

    epoch = args.epoch
    next_validation_time: Optional[str] = None
    if epoch == 0:
        epoch, next_validation_time = get_current_epoch_info(api)
    else:
        next_validation_time = get_epoch_validation_time(api, int(epoch))

    log(f"Epoch: {epoch} (live)")
    log(f"Fetching flips and counting authors (threshold > {thr}) ...")

    counts: Counter[str] = Counter()
    seen = 0

    for fl in paged_flips(api, epoch=epoch, page_size=args.page_size, sleep_per_page=args.sleep_per_page):
        seen += 1
        author = try_get_author(fl)
        cid = try_get_cid(fl)
        if not author or not cid:
            continue
        counts[author] += 1
        if seen % 2000 == 0:
            log(f"processed flips: {seen} (unique authors so far: {len(counts)})")

    total_authors = len(counts)
    authors_gt = [a for a, c in counts.items() if c > thr]
    authors_gt_n = len(authors_gt)
    total_extra_flips = sum(max(0, counts[a] - thr) for a in authors_gt)

    log(f"Done. flips_seen={seen} unique_authors={total_authors}")
    log(f"authors_with_flipCount>{thr}: {authors_gt_n}")
    log(f"total_extra_flips_over_{thr}: {total_extra_flips}")

    ranked = sorted(((a, counts[a]) for a in counts), key=lambda x: (x[1], x[0]), reverse=True)

    topn = max(0, int(args.top))
    if topn:
        print("\n=== TOP AUTHORS by flipCount (live) ===")
        for i, (a, c) in enumerate(ranked[:topn], start=1):
            extra = max(0, c - thr)
            mark = "  EXTRA" if extra > 0 else ""
            print(f"{i:4d}  flips={c:2d}  extra={extra:2d}  {a}{mark}")

    # Always write CSV for authors over threshold
    csv_path_over = os.path.join(out_dir, f"live_extra_flips_epoch{epoch}_gt{thr}.csv")

    # Optional new CSV for all authors with flips + stake
    csv_path_all = os.path.join(out_dir, f"live_flip_authors_epoch{epoch}.csv")

    meta_path = os.path.join(out_dir, f"live_extra_flips_epoch{epoch}_gt{thr}.meta.json")

    # Stake fetching plan
    do_stake_over = bool(args.fetch_stake)
    do_stake_all = bool(args.fetch_stake_all)

    if do_stake_all:
        do_stake_over = False  # avoid double work, we will already cover everyone

    grade_leaderboard: Dict[str, Any] = {"enabled": False, "topIdentities": []}
    if not args.disable_grade_leaderboard:
        grade_epoch = max(0, epoch - int(args.grade_epoch_offset))

        if grade_epoch <= 0:
            grade_leaderboard = {
                "enabled": False,
                "epoch": grade_epoch,
                "topLimit": max(0, int(args.grade_top)),
                "topFlipsLimit": max(0, int(args.grade_top_flips)),
                "topIdentities": [],
                "identityLookup": [],
                "topFlips": [],
                "note": "Grade leaderboard skipped because computed epoch is <= 0.",
            }
        else:
            grade_leaderboard = build_grade_identity_leaderboard(
                api=api,
                epoch=grade_epoch,
                page_size=args.page_size,
                sleep_per_page=args.sleep_per_page,
                allowed_statuses=grade_statuses,
                include_zero=bool(args.grade_include_zero),
                top_n=args.grade_top,
                top_flips_n=args.grade_top_flips,
                out_dir=out_dir,
            )
            log(f"Wrote grade identity leaderboard CSV: {grade_leaderboard.get('identityLeaderboardCsvPath', '')}")

    stake_cache: Dict[str, Tuple[float, str]] = {}

    def get_stake_cached(addr: str) -> Tuple[float, str]:
        if addr in stake_cache:
            return stake_cache[addr]
        s, note = fetch_stake_for_address_best_effort(api, addr)
        stake_cache[addr] = (s, note)
        if args.stake_sleep > 0:
            time.sleep(args.stake_sleep)
        return s, note

    # 1) Write authors over threshold CSV
    rows_over: List[List[Any]] = []
    stake_total_over = 0.0
    stake_rows_over = 0

    for a in sorted(authors_gt, key=lambda x: (counts[x], x), reverse=True):
        c = counts[a]
        extra = max(0, c - thr)
        stake = ""
        extra_per_stake = ""
        stake_note = ""

        if do_stake_over:
            s, note = get_stake_cached(a)
            stake_note = note
            stake = f"{s:.8f}"
            if s > 0:
                extra_per_stake = f"{(extra / s):.12f}"
                stake_total_over += s
                stake_rows_over += 1

        rows_over.append([
            a,
            c,
            extra,
            stake,
            extra_per_stake,
            stake_note,
            f"https://scan.idena.io/address/{a}",
        ])

    write_csv(
        csv_path_over,
        header=["address", "flipCount", "extraFlipsOverThreshold", "stake", "extraFlipsPerStake", "stakeNote", "scan_url"],
        rows=rows_over,
    )

    # 2) Optionally write all authors stake CSV
    stake_total_all = 0.0
    stake_rows_all = 0

    if do_stake_all:
        log(f"Fetching stake for ALL flip authors: {len(counts)} addresses")
        rows_all: List[List[Any]] = []
        for i, (a, c) in enumerate(ranked, start=1):
            s, note = get_stake_cached(a)
            if s > 0:
                stake_total_all += s
                stake_rows_all += 1
            rows_all.append([
                a,
                c,
                f"{s:.8f}",
                note,
                f"https://scan.idena.io/address/{a}",
            ])
            if i % 200 == 0:
                log(f"stake progress: {i}/{len(counts)}")

        write_csv(
            csv_path_all,
            header=["address", "flipCount", "stake", "stakeNote", "scan_url"],
            rows=rows_all,
        )
        log(f"Wrote ALL authors CSV: {csv_path_all}")

    current_point = {
        "timestamp": utc_ts(),
        "flipsSeen": int(seen),
        "uniqueAuthors": int(total_authors),
    }

    epoch_key = str(epoch)
    epoch_points = normalize_progress_points(history_by_epoch.get(epoch_key, []))
    if not epoch_points:
        epoch_points = [current_point]
    else:
        last_point = epoch_points[-1]
        if last_point["flipsSeen"] == current_point["flipsSeen"] and last_point["uniqueAuthors"] == current_point["uniqueAuthors"]:
            epoch_points[-1] = current_point
        else:
            epoch_points.append(current_point)
    history_by_epoch[epoch_key] = epoch_points[-1500:]

    known_epochs = sorted([int(k) for k in history_by_epoch.keys() if str(k).isdigit()], reverse=True)
    keep_epochs = set(known_epochs[:6])
    for key in list(history_by_epoch.keys()):
        if str(key).isdigit() and int(key) not in keep_epochs:
            del history_by_epoch[key]

    progress_series = build_progress_series(history_by_epoch, epoch)
    next_refresh_at = unix_to_iso(time.time() + min_refresh_seconds) if min_refresh_seconds > 0 else None

    # Meta
    meta = {
        "timestamp": current_point["timestamp"],
        "epoch": epoch,
        "threshold": thr,
        "baseUrl": args.base_url,
        "counts": {
            "flipsSeen": seen,
            "uniqueAuthors": total_authors,
            "authorsOverThreshold": authors_gt_n,
            "totalExtraFlips": total_extra_flips,
        },
        "session": {
            "nextValidationTime": next_validation_time,
        },
        "stake": {
            "fetchStakeOverThresholdEnabled": bool(do_stake_over),
            "fetchStakeAllEnabled": bool(do_stake_all),
            "stakeSleepSeconds": float(args.stake_sleep),
            "overThreshold": {
                "authorsWithStake>0": stake_rows_over,
                "totalStake": stake_total_over,
                "extraFlipsPerTotalStake": (total_extra_flips / stake_total_over) if (do_stake_over and stake_total_over > 0) else None,
            },
            "allAuthors": {
                "authorsWithStake>0": stake_rows_all,
                "totalStake": stake_total_all,
            },
        },
        "gradeLeaderboard": grade_leaderboard,
        "progress": {
            "cacheUsed": False,
            "minRefreshSeconds": min_refresh_seconds,
            "secondsUntilNextRefresh": min_refresh_seconds,
            "nextRefreshAt": next_refresh_at,
            "lastFreshScanAt": current_point["timestamp"],
            "lastRequestAt": current_point["timestamp"],
            "historyFile": args.cache_file,
            "series": progress_series,
        },
        "note": "Live snapshot. Data can change until flip submission closes.",
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    if not args.disable_cache:
        state["historyByEpoch"] = history_by_epoch
        state["lastScan"] = {
            "cacheKey": cache_key,
            "freshTimestamp": current_point["timestamp"],
            "meta": meta,
        }
        write_json_file(args.cache_file, state)

    log(f"Wrote CSV (over threshold): {csv_path_over}")
    log(f"Wrote META: {meta_path}")

    if do_stake_over and stake_total_over > 0:
        log(f"extraFlipsPerTotalStake(over-threshold authors) = {total_extra_flips / stake_total_over:.12f}")

    if do_stake_all:
        log(f"totalStake(all flip authors with stake>0) = {stake_total_all:.8f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
