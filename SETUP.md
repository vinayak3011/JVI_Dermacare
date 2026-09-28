# DermCare Setup Guide

This project contains:

- **FastAPI backend** in `app.py`
- **React/Vite frontend** in `frontend/`
- **TensorFlow model** in `final_model_kaggle_version1/`
- **SQLite database** created automatically at `data/dermcare.sqlite3`
- **Supabase/PostgreSQL schema** in `supabase_schema.sql` for hosted deployments

The recommended development setup uses two local servers:

- React/Vite: `http://localhost:5173`
- FastAPI: `http://localhost:8000`

## 1. Prerequisites

Install these before starting:

| Tool | Recommended version | Check command |
| --- | --- | --- |
| Python | 3.12.x | `python --version` |
| Node.js | 20.19+ or 22+ | `node --version` |
| npm | Installed with Node.js | `npm --version` |
| Git | Optional | `git --version` |

TensorFlow can require several gigabytes of disk space. The model files must remain in:

```text
final_model_kaggle_version1/model.json
final_model_kaggle_version1/group1-shard1of4
final_model_kaggle_version1/group1-shard2of4
final_model_kaggle_version1/group1-shard3of4
final_model_kaggle_version1/group1-shard4of4
```

## 2. Open the project

## 2a. Create the Supabase database

1. Create a project at [supabase.com](https://supabase.com).
2. Open **SQL Editor**, paste the contents of `supabase_schema.sql`, and run it.
3. In **Project Settings > Database**, copy the URI connection string.
4. Copy `.env.example` to `.env` and set `SUPABASE_DATABASE_URL`.

The current app keeps SQLite as the local development fallback. The Supabase schema is ready for the backend migration, and the database URI must remain server-side. Do not place it in `frontend/.env` or commit `.env`.

For production, create a private Storage bucket called `dermcare-scans` and store only object paths in `scans.image_path`. Keep the service-role key server-side.


## 3. Create and activate the Python environment

Create the virtual environment once:

```powershell
py -3.12 -m venv .venv
```

If `py -3.12` is unavailable, use:

```powershell
python -m venv .venv
```

Activate it in the current PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

You should see `(.venv)` at the beginning of the terminal prompt.

Upgrade pip and install the backend dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Verify the Python installation:

```powershell
python -c "import fastapi, tensorflow, uvicorn; print('Backend dependencies are ready')"
```

## 4. Install React dependencies

Open a second PowerShell terminal and run:

```powershell
cd D:\Projects\dermcare\frontend
npm install
```

Verify the React build:

```powershell
npm run build
```

A successful build creates:

```text
frontend/dist/index.html
frontend/dist/assets/
```

## 5. Run in development mode

### Terminal 1: FastAPI backend

From the project root, with `.venv` activated:

```powershell
cd D:\Projects\dermcare
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

The backend API is available at:

```text
http://localhost:8000
```

FastAPI documentation is available at:

```text
http://localhost:8000/docs
```

### Terminal 2: React frontend

```powershell
cd D:\Projects\dermcare\frontend
npm run dev
```

Open this address in your browser:

```text
http://localhost:5173
```

The Vite development server forwards these requests to FastAPI:

- `/api/*`
- `/uploads/*`

Keep both terminals running while developing.

## 6. Run production-style locally

Build the React application:

```powershell
cd D:\Projects\dermcare\frontend
npm run build
```

Start FastAPI from the project root:

```powershell
cd D:\Projects\dermcare
.\.venv\Scripts\Activate.ps1
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://localhost:8000
```

In this mode FastAPI serves the compiled React app from `frontend/dist/`.

## 7. First use

1. Open the application.
2. Select **Create account**.
3. Enter your name, email, location, phone, age, date of birth, and an 8+ character password.
4. Sign in.
5. Open **Skin Scan**.
6. Choose an image or drag it into the upload area.
7. Give the scan a name.
8. Select **Analyse this image**.
9. Use **Start a new scan** after the result is displayed.
10. Open **Profile** to view, rename, or delete previous scans.

The first scan may take longer because TensorFlow loads the model into memory. Later scans reuse the loaded model.

## 8. Files created automatically

The backend creates these files and folders when needed:

```text
data/dermcare.sqlite3
data/uploads/
frontend/dist/
```

The SQLite database stores users and scan metadata. Uploaded images are stored in `data/uploads/` and are protected by the logged-in user's session.

## 9. Useful checks

Check backend syntax:

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py predict.py
```

Check the React build:

```powershell
cd frontend
npm run build
```

Check the backend health through the browser:

```text
http://localhost:8000/docs
```

## 10. Common Windows problems

### PowerShell will not activate `.venv`

Run this only for the current terminal session, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### `ModuleNotFoundError: No module named 'fastapi'`

The virtual environment is not active, or dependencies were installed into another Python installation. Run:

```powershell
cd D:\Projects\dermcare
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -c "import fastapi; print(fastapi.__version__)"
```

### `npm` cannot find `package.json`

Run npm commands inside the frontend directory:

```powershell
cd D:\Projects\dermcare\frontend
npm install
npm run dev
```

### Scan returns `503`

Check that all model files exist:

```powershell
Get-ChildItem .\final_model_kaggle_version1
```

The backend must be started from `D:\Projects\dermcare`, and the Python environment must contain TensorFlow:

```powershell
.\.venv\Scripts\python.exe -c "import tensorflow; print(tensorflow.__version__)"
```

### Port already in use

Use another backend port:

```powershell
python -m uvicorn app:app --reload --port 8001
```

If using the Vite development proxy, update `frontend/vite.config.js` to point to `http://127.0.0.1:8001` before starting Vite.

## 11. Restarting after code changes

- FastAPI reloads Python changes automatically when using `--reload`.
- Vite updates React changes automatically while `npm run dev` is running.
- Run `npm run build` again whenever testing production-style serving.
- Do not delete `data/` unless you intentionally want to remove the local database and uploaded scan images.
