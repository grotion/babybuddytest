# Baby Buddy + STaD Test Setup & Run Guide

This guide separates:

- ✅ One-time setup (run once)
- 🔁 Daily usage (run every time)

---

# ✅ ONE-TIME SETUP

## 1. Check Docker

<pre>
docker --version
docker compose version
</pre>

---

## 2. Install Python environment (Pipenv)

<pre>
pipenv install --dev
</pre>

---

## 3. Install Node (NVM)

<pre>
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"
nvm --version
nvm install 18
nvm use 18
</pre>

---

## 4. Install frontend dependencies

<pre>
npm install -g gulp-cli
npm install
</pre>

---

## 5. Install testing tools (for STaD)

<pre>
pipenv install --dev pytest pytest-django pytest-cov mutmut
</pre>

---

## 6. Set Django settings

<pre>
export DJANGO_SETTINGS_MODULE=babybuddy.settings.development
</pre>

(Optional: add this to ~/.zshrc so you don’t repeat it)

---

## 7. Initialize database (Could skip)

<pre>
pipenv run python manage.py migrate
</pre>

---

## 8. Run application (optional check)

<pre>
gulp migrate
gulp
</pre>

Open:
http://127.0.0.1:8000

Login:
admin / admin

---

# 🔁 RUN EVERY TIME (TESTING)

## Run all tests

<pre>
pipenv run pytest stad_test
</pre>

---

## Run specific test groups

### Black-box tests

<pre>
pipenv run pytest stad_test/blackbox
</pre>

### White-box tests

<pre>
pipenv run pytest stad_test/whitebox
</pre>

---

## Run with coverage

<pre>
pipenv run pytest stad_test --cov=api --cov-branch --cov-report=term-missing
</pre>

---

## Run mutation testing

<pre>
pipenv run mutmut run
pipenv run mutmut results
</pre>

---

# ❌ DO NOT RUN EVERY TIME

Only run these again if something breaks:

<pre>
pipenv install --dev
npm install
nvm install
pipenv run python manage.py migrate
</pre>

---

# ⚠️ COMMON ISSUES

## 1. Django not found

Wrong:
pytest stad_test

Correct:
pipenv run pytest stad_test

---

## 2. Wrong settings module

<pre>
export DJANGO_SETTINGS_MODULE=babybuddy.settings.development
</pre>

---

## 3. Database errors

<pre>
pipenv run python manage.py migrate
</pre>

---

## 4. Import errors

Make sure you run commands from the project root (where manage.py is located)

---

# 🚀 OPTIONAL (QUALITY OF LIFE)

Add this to ~/.zshrc:

<pre>
alias pt="export DJANGO_SETTINGS_MODULE=babybuddy.settings.development && pipenv run pytest stad_test"
</pre>

Then just run:
pt
