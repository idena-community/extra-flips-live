# Idena Community Tools - Extra Flips Live Scanner

> A real-time dashboard to monitor "Extra Flips" on the Idena Blockchain, built with **Nuxt 3**.
> This project is a web interface wrapper around the original Python script by **ubiubi18**.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Nuxt](https://img.shields.io/badge/Nuxt-3.x-green.svg)
![Python](https://img.shields.io/badge/Python-3.x-yellow.svg)

## 📖 About The Project

This tool allows Idena community members to scan the current epoch in real-time to identify authors who have submitted more flips than the required threshold.

It solves the problem of tracking the "Extra Flips" reward pool potential before the validation session.

**Core Logic:**
The backend logic relies on the Python scanner script from the **[ubiubi18/flip_extra_flips_live.py](https://github.com/ubiubi18/flip_extra_flips_live.py)** repository. We have integrated this script into a modern Nuxt application to provide a user-friendly, visual interface.

### Key Features
* **Real-time Scanning**: Fetches live data from the Idena blockchain.
* **Hybrid Architecture**: Combines the reactive frontend of Nuxt.js with the data processing power of Python.
* **Visual Dashboard**: Displays key metrics (Total Extra Flips, Authors count, Current Epoch) in a clean UI.
* **Auto-Cleaning**: Automatically manages temporary data files to keep the server clean.

---

## ⚙️ Architecture

This project uses a unique approach to bridge Node.js and Python:

1.  **Frontend (Vue/Nuxt)**: The user requests a scan via the UI.
2.  **Server API (Nitro)**: Nuxt triggers a server-side route (`/api/scan`).
3.  **Child Process**: Node.js spawns a Python subprocess to execute the scanner script.
4.  **Data Exchange**: Python writes the results to a JSON file, which Node.js reads and returns to the frontend.

---

## 🚀 Getting Started

Since this project requires **both** Node.js and Python to run simultaneously, please follow these instructions carefully.

### Prerequisites

* **Node.js** (v18 or higher)
* **npm** or **yarn**
* **Python 3** (Must be accessible via the command `python3` or `python`)
* **Git**

### Installation

1.  **Clone the repository**
    ```bash
    git clone https://github.com/idena-community/extra-flips-live.git
    cd extra-flip-live
    ```

2.  **Install Node dependencies**
    ```bash
    npm install
    ```

3.  **Verify Python**
    Ensure Python is installed and has internet access (the script uses the standard library, so no `pip install` is usually needed unless you extend the script).
    ```bash
    python3 --version
    ```

---

## 🏃‍♂️ Usage

### Development Mode
To start the development server with hot-reload:

```bash
npm run dev
```
Visit http://localhost:3000/scanner to see the dashboard.
Production Build

To build the application for production:
Bash

npm run build
node .output/server/index.mjs


## 📂 Project Structure
Plaintext

extrafliplive/
├── scripts/
│   ├── flip_extra_flips_live.py  # The core logic (Credit: ubiubi18)
│   └── out/                      # Temporary output folder (Ignored by Git)
├── server/
│   └── api/
│       └── scan.ts               # The Node-to-Python bridge
├── pages/
│   └── scanner.vue               # The Dashboard UI
├── nuxt.config.ts                # Nuxt configuration
└── package.json

## 🤝 Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are greatly appreciated.

    Fork the Project

    Create your Feature Branch (git checkout -b feature/AmazingFeature)

    Commit your Changes (git commit -m 'Add some AmazingFeature')

    Push to the Branch (git push origin feature/AmazingFeature)

    Open a Pull Request

## 📜 License
Distributed under the MIT License. See LICENSE for more information.

## 👏 Acknowledgments
Special thanks to the original creator of the scanning logic:

    ubiubi18 - For creating the original Python script. This project is a UI wrapper around their work. 

    Idena Community - For the inspiration and support.
