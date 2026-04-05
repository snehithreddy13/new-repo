# Full Ambulance Dispatch Simulator (Backend + Frontend + Simulation)

This repository now includes a complete runnable scaffold for a multi-hospital ambulance simulator with:

- **Backend (Flask + Socket.IO)** for dispatch logic and APIs
- **Frontend (React + Leaflet)** for live map dashboard + popups
- **Simulation script** that generates random emergency incidents

## Project Structure

```text
backend/
  app.py
  requirements.txt
frontend/
  package.json
  public/index.html
  src/index.js
  src/App.js
simulation/
  simulate.py
  requirements.txt
```

## 1) Run backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Backend runs at `http://localhost:5000`.

## 2) Run frontend

```bash
cd frontend
npm install
npm start
```

Frontend runs at `http://localhost:3000` and subscribes to Socket.IO updates from backend.

## 3) Run incident simulator

```bash
cd simulation
pip install -r requirements.txt
python simulate.py
```

This continuously posts random high/medium/low incidents into backend.

## API Endpoints

- `GET /health`
- `GET /api/state`
- `POST /api/incidents`

Example POST body:

```json
{
  "lat": 37.772,
  "lng": -122.418,
  "severity": "high"
}
```
