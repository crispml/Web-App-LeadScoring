import os
import json

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from flow import run_sales_pipeline


app = FastAPI(
    title="AI Sales Lead Qualification"
)


# ============================================================
# SESSION
# ============================================================

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv(
        "SESSION_SECRET_KEY",
        "development-secret-key"
    )
)


templates = Jinja2Templates(
    directory="templates"
)


USERS_FILE = "users.json"


# ============================================================
# USER MANAGEMENT
# ============================================================

def load_users():

    with open(USERS_FILE, "r") as file:

        return json.load(file)


def save_users(users):

    with open(USERS_FILE, "w") as file:

        json.dump(
            users,
            file,
            indent=4
        )


# ============================================================
# LOGIN PAGE
# ============================================================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request
        }
    )


# ============================================================
# LOGIN
# ============================================================

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):

    users = load_users()

    user = users.get(username)

    # --------------------------------------------------------
    # User doesn't exist
    # --------------------------------------------------------

    if user is None:

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "error": "Invalid username or password."
            },
            status_code=401
        )


    # --------------------------------------------------------
    # Get password from environment
    # --------------------------------------------------------

    password_env = user["password_env"]

    correct_password = os.getenv(
        password_env
    )


    # --------------------------------------------------------
    # Validate password
    # --------------------------------------------------------

    if password != correct_password:

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "error": "Invalid username or password."
            },
            status_code=401
        )


    # --------------------------------------------------------
    # Successful login
    # --------------------------------------------------------

    request.session["authenticated"] = True

    request.session["username"] = username

    request.session["role"] = user["role"]


    return RedirectResponse(
        url="/",
        status_code=303
    )


# ============================================================
# LOGOUT
# ============================================================

@app.get("/logout")
def logout(request: Request):

    request.session.clear()

    return RedirectResponse(
        url="/login",
        status_code=303
    )


# ============================================================
# HOME
# ============================================================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    # --------------------------------------------------------
    # Authentication check
    # --------------------------------------------------------

    if not request.session.get("authenticated"):

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    # --------------------------------------------------------
    # Get current user
    # --------------------------------------------------------

    username = request.session["username"]

    users = load_users()

    user = users[username]


    # --------------------------------------------------------
    # Calculate remaining reports
    # --------------------------------------------------------

    if user["max_reports"] is None:

        reports_remaining = "Unlimited"

    else:

        reports_remaining = (
            user["max_reports"]
            - user["reports_used"]
        )


    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "reports_remaining": reports_remaining,
            "username": username
        }
    )


# ============================================================
# RUN LEAD SCORING
# ============================================================

@app.post("/run", response_class=HTMLResponse)
def run_pipeline(
    request: Request,
    name: str = Form(...),
    job_title: str = Form(...),
    company: str = Form(...),
    email: str = Form(...),
    use_case: str = Form(...)
):

    # --------------------------------------------------------
    # Authentication check
    # --------------------------------------------------------

    if not request.session.get("authenticated"):

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    # --------------------------------------------------------
    # Identify user
    # --------------------------------------------------------

    username = request.session["username"]

    users = load_users()

    user = users[username]


    # --------------------------------------------------------
    # Check report quota BEFORE calling CrewAI
    # --------------------------------------------------------

    if user["max_reports"] is not None:

        if user["reports_used"] >= user["max_reports"]:

            reports_remaining = 0

            return templates.TemplateResponse(
                request=request,
                name="index.html",
                context={
                    "request": request,
                    "username": username,
                    "reports_remaining": reports_remaining,
                    "quota_error": (
                        "Report limit reached. "
                        "You have used all "
                        f"{user['max_reports']} "
                        "allocated lead reports."
                    )
                },
                status_code=403
            )


    # --------------------------------------------------------
    # Create lead
    # --------------------------------------------------------

    lead_data = {

        "name": name,

        "job_title": job_title,

        "company": company,

        "email": email,

        "use_case": use_case
    }


    # --------------------------------------------------------
    # RUN CREWAI
    # --------------------------------------------------------

    result = run_sales_pipeline(
        lead_data
    )


    # --------------------------------------------------------
    # Increment report counter
    #
    # Only count a report AFTER CrewAI successfully runs.
    # --------------------------------------------------------

    if user["max_reports"] is not None:

        user["reports_used"] += 1

        save_users(users)


    # --------------------------------------------------------
    # Calculate remaining reports
    # --------------------------------------------------------

    if user["max_reports"] is None:

        reports_remaining = "Unlimited"

    else:

        reports_remaining = (
            user["max_reports"]
            - user["reports_used"]
        )


    # --------------------------------------------------------
    # Display report
    # --------------------------------------------------------

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "result": result,
            "username": username,
            "reports_remaining": reports_remaining
        }
    )