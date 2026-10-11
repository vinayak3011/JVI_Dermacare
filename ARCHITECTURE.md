# DermCare Project Structure and Architecture

## 1. Project overview

DermCare is a full-stack skin-image screening application:

- **Frontend:** React with Vite.
- **Backend:** FastAPI running on Python.
- **Inference:** TensorFlow/Keras reconstructs and runs the bundled model.
- **Persistence:** SQLite for local development, with an optional PostgreSQL/Supabase connection.
- **Uploaded images:** Stored locally under `data/uploads/`.
- **Authentication:** Implemented by the FastAPI backend with a signed session cookie.

The application is a screening aid, not a medical diagnosis service. The model returns the most likely skin-lesion classes and their probabilities.

## 2. Repository tree

Generated folders and third-party dependencies are intentionally abbreviated. They should not be treated as application source.

```text
dermcare/
├── app.py                         # FastAPI application and backend API
├── predict.py                     # Model loading and image prediction functions
├── requirements.txt               # Python backend dependencies
├── package.json                   # Root JavaScript dependency manifest
├── package-lock.json              # Root npm lockfile
├── supabase_schema.sql            # Hosted PostgreSQL/Supabase schema
├── SETUP.md                       # Installation and local run instructions
├── README.md                      # Project title/entry point
├── .env.example                   # Safe configuration template
├── .env.local                     # Local secrets/configuration; never commit or expose
│
├── frontend/
│   ├── index.html                 # Browser HTML shell and font imports
│   ├── package.json               # React/Vite frontend dependencies and scripts
│   ├── package-lock.json          # Frontend npm lockfile
│   ├── vite.config.js             # Vite server, port, and backend proxy
│   ├── prisma.config.ts          # Prisma skill configuration; not the runtime data layer
│   ├── src/
│   │   ├── main.jsx              # React entry point, UI components, API calls, client state
│   │   └── styles.css            # Global styles, layout, responsive rules, theme variables
│   └── dist/                     # Generated production frontend build; not source
│
├── final_model_kaggle_version1/
│   ├── model.json                 # TensorFlow.js model topology and weight manifest
│   └── group1-shard*              # Four binary model-weight shards
│
├── data/
│   ├── dermcare.sqlite3           # Generated local database
│   └── uploads/                   # Generated uploaded images
│
├── .venv/                         # Local Python virtual environment; generated
└── node_modules/                  # Root npm dependencies; generated
```

## 3. Architectural layers

The current implementation is intentionally compact rather than split into multiple backend packages.

```text
Browser
  │
  │ React UI / fetch()
  ▼
Vite development server
  │
  │ /api/* and /uploads/* proxy to port 8000
  ▼
FastAPI application (app.py)
  ├── Authentication and signed session cookies
  ├── Request validation and user authorization
  ├── Database connection abstraction
  ├── Scan upload and local file storage
  ├── Lazy model loading and prediction orchestration
  └── Static frontend serving in production mode
       │
       ├── SQLite: data/dermcare.sqlite3
       ├── PostgreSQL/Supabase: SUPABASE_DATABASE_URL, when configured
       ├── Uploaded images: data/uploads/
       └── Model bundle: final_model_kaggle_version1/
```

### Frontend layer

`frontend/src/main.jsx` contains the client entry point and the current page components:

- `Auth`: sign-in and account-registration forms.
- `App`: authenticated shell, hash-based navigation, session bootstrap, logout, and toast messages.
- `Home`: landing page.
- `About`: product explanation and feature cards.
- `Blogs`: static journal/education cards.
- `Scan`: image selection, preview, submission, and result display.
- `Result`: prediction result presentation.
- `Profile`: user details, scan history, rename/delete actions, and local appearance preferences.
- `Field` and `Intro`: reusable presentation helpers.

The frontend uses URL hashes (`#home`, `#about`, `#scan`, `#blogs`, and `#profile`) instead of a client-side router. API calls are made through the local `api()` helper, which parses JSON and converts non-2xx responses into JavaScript errors.

### Backend layer

`app.py` currently combines the HTTP layer, authentication helpers, persistence operations, upload handling, and inference orchestration:

- `connection()` chooses PostgreSQL/Supabase when `SUPABASE_DATABASE_URL` is set; otherwise it opens SQLite.
- `initialise_database()` creates the `users` and `scans` tables if they do not already exist.
- `current_user()` validates the `session` cookie and loads the authenticated user.
- `public_user()` and `public_scan()` convert database rows into browser-safe response objects.
- Scan inference imports `predict.py` lazily on the first scan and then reuses the loaded model in process memory.

### Model layer

`predict.py` is also usable as a command-line program. Its responsibilities are:

1. Read the TensorFlow.js `model.json` bundle.
2. Reconstruct the Keras model from `modelTopology`.
3. Read all four binary weight shards from `weightsManifest`.
4. Assign weights to the reconstructed model.
5. Resize an image to `224 x 224`, convert it to RGB, and normalize pixels to `[-1, 1]`.
6. Return the top `k` classes from the seven known `CLASS_NAMES`.

## 4. Backend API surface

| Method | Path | Purpose | Authentication |
|---|---|---|---|
| `GET` | `/` | Serve `frontend/dist/index.html` when available, otherwise the source HTML shell | Public |
| `POST` | `/api/auth/register` | Create a user from multipart form fields | Public |
| `POST` | `/api/auth/login` | Verify credentials and return a signed session token | Public |
| `GET` | `/api/auth/me` | Restore the current signed-in user | Session cookie |
| `GET` | `/api/scans` | List the current user's scans, newest first | Session cookie |
| `POST` | `/api/scans` | Validate an image, run inference, save the scan, and return the result | Session cookie |
| `PATCH` | `/api/scans/{scan_id}` | Rename one scan owned by the current user | Session cookie |
| `DELETE` | `/api/scans/{scan_id}` | Delete a scan and its uploaded image | Session cookie |
| `GET` | `/uploads/{filename}` | Serve an image only when it belongs to the current user | Session cookie |

### Request and response flow

#### Registration and login

1. The React `Auth` component submits a `FormData` request.
2. FastAPI validates the submitted fields.
3. The password is stored as a PBKDF2-HMAC-SHA256 derived value with a random salt.
4. Login creates a signed, seven-day session payload.
5. The browser stores that value in the `session` cookie.
6. On application startup, `App` calls `/api/auth/me` to restore the session.

#### Skin scan

1. The user selects or drops a JPG, PNG, or WebP image in `Scan`.
2. The frontend sends the image and `subject_name` to `POST /api/scans`.
3. The backend checks the MIME type and enforces a 10 MB limit.
4. The image receives a random filename and is written to `data/uploads/`.
5. On the first scan only, the backend loads the model from `final_model_kaggle_version1/model.json`.
6. `predict_image()` returns the top three classes by default.
7. The backend stores scan metadata and serialized predictions.
8. The response includes an authenticated `image_url` for the result preview.
9. If model inference fails, the uploaded file is removed and a `503` response is returned.

#### Scan history

1. `Profile` requests `/api/scans`.
2. The backend filters by the authenticated user's ID.
3. Rename and delete operations include both `scan_id` and `user_id` in their database queries.
4. Image deletion removes the local file after the database record is removed.

## 5. Data model

The local SQLite schema and hosted Supabase schema represent the same two core entities.

### `users`

Stores account identity and profile fields:

```text
id, name, email, location, phone, age, date_of_birth,
password_hash, created_at
```

`email` is unique. `age` is validated between 1 and 120. Password hashes are never returned to the frontend.

### `scans`

Stores one model analysis associated with one user:

```text
id, user_id, subject_name, image_path,
original_filename, predictions, created_at
```

Relationship:

```text
users 1 ─────────── * scans
```

Deleting a user cascades to their scans in the hosted schema. The backend also deletes the local image file when a scan is deleted.

### Storage modes

- **Local mode:** SQLite is selected when `SUPABASE_DATABASE_URL` is absent. Predictions are stored as JSON text.
- **Hosted database mode:** PostgreSQL/Supabase is selected when `SUPABASE_DATABASE_URL` is present. Predictions are stored as JSONB.
- **Current image storage:** The FastAPI code writes images to `data/uploads/` in both modes. `supabase_schema.sql` documents a future/private Supabase Storage bucket, but the current backend does not upload objects there.

## 6. Configuration and generated state

| File or variable | Role |
|---|---|
| `.env.local` | Local server-side values; contains sensitive configuration and must remain private |
| `.env.example` | Non-secret configuration template |
| `SUPABASE_DATABASE_URL` | Switches persistence from SQLite to PostgreSQL/Supabase |
| `SUPABASE_URL`, storage keys, and JWKS values | Reserved for hosted integrations; keep server-side |
| `frontend/vite.config.js` | Uses repository-root environment lookup and proxies API/image requests during development |
| `data/dermcare.sqlite3` | Runtime-generated local database |
| `data/uploads/` | Runtime-generated image files |
| `frontend/dist/` | Generated by `npm run build`; served by FastAPI in production-style mode |

Never copy server database URLs, service-role keys, or other secrets into frontend source or browser-exposed Vite variables.

## 7. Development and production-style execution

### Development

Run two processes:

```text
React/Vite   http://localhost:5173
FastAPI      http://localhost:8000
```

Vite proxies `/api` and `/uploads` to FastAPI, so the browser can use relative URLs.

### Production-style local run

1. Build the frontend with `npm run build` from `frontend/`.
2. Start FastAPI from the repository root.
3. FastAPI serves the compiled `frontend/dist/index.html` and its assets.

## 8. Important current design characteristics

- `app.py` is the main backend composition root and is the largest coupling point.
- `frontend/src/main.jsx` is a single frontend module containing all screens and API interaction.
- There is no separate service or repository package; SQL is executed directly from endpoint/helper functions.
- Model loading is lazy and process-local, so the first scan is slower than later scans.
- The session secret is generated at process startup. Restarting the backend invalidates existing sessions.
- `frontend/prisma.config.ts` configures Prisma tooling, but runtime persistence currently uses the SQL connection logic in `app.py`.
- The database and image uploads under `data/` are runtime state, not source code.

## 9. Where to start when changing the project

| Change | Primary files |
|---|---|
| Add or modify an API endpoint | `app.py` |
| Change authentication/session behavior | `app.py`, `frontend/src/main.jsx` |
| Change scan validation or persistence | `app.py`, `supabase_schema.sql` |
| Change model loading or preprocessing | `predict.py`, `app.py` |
| Add a frontend page or interaction | `frontend/src/main.jsx` |
| Change visual design or responsive layout | `frontend/src/styles.css` |
| Change local/hosted setup | `.env.example`, `SETUP.md`, `supabase_schema.sql` |
| Change frontend development proxy or port | `frontend/vite.config.js` |

