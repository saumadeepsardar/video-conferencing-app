# LAN Multi-User Communication Suite

A server-based application for complete team collaboration over a Local Area Network (LAN), with no internet connection required.

## 📌 Introduction

The goal of this project is to develop a robust, standalone, and server-based multi-user communication application that operates exclusively over a Local Area Network (LAN). This system provides a comprehensive suite of collaboration tools, enabling teams to communicate and share information in environments where internet access is unavailable, unreliable, or restricted.

The application is a one-stop solution for real-time collaboration, integrating:
* Video Conferencing
* Audio Calls
* Group & Private Chat
* Presentation/Screen Sharing
* File Sharing

## 🛠️ Getting Started

Follow these instructions to get a local copy up and running.

### Prerequisites

* [Python 3.12+](https://www.python.org/downloads/)
* [Git](https://git-scm.com/downloads)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/saumadeepsardar/video-conferencing-app.git
    cd video-conferencing-app
    ```

2.  **Create a virtual environment:**
    * This project is set up to use a virtual environment named `video`.
    ```bash
    python -m venv video
    ```

3.  **Activate the virtual environment:**
    ```bash
    # On Windows
    .\video\Scripts\activate
    
    # On macOS/Linux
    source video/bin/activate
    ```

4.  **Install dependencies:**
    * Make sure your virtual environment is active before running this.
    ```bash
    pip install -r requirements.txt
    ```

---

## 🖥️ How to Run

There are two ways to run the application. The server **must** be running before any clients can connect.

### Option 1: Use the Launcher Scripts (Recommended)

These scripts automatically activate the virtual environment and present a menu to start the server or client.

* **On Windows:**
    > Simply double-click the `start.bat` file.

* **On macOS/Linux:**
    ```bash
    # First, make the script executable (only need to do this once)
    chmod +x start.sh

    # Now, run it
    ./start.sh
    ```
    You will then be prompted to choose `1` for Client or `2` for Server.

### Option 2: Run Manually

You can run the server and client components manually in separate terminal windows.

1.  **Activate the virtual environment** in each terminal you open:
    ```bash
    # On Windows
    .\video\Scripts\activate
    
    # On macOS/Linux
    source video/bin/activate
    ```

2.  **Start the Server:**
    * In your first terminal, run:
    ```bash
    python server.py
    ```

3.  **Start the Client:**
    * Open a **new terminal** and activate the virtual environment again.
    * Run the following to connect to the server:
    ```bash
    python client.py
    ```
    * You can repeat this step on multiple computers (or in multiple terminals) to simulate different users.