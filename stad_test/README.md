# Baby Buddy + STaD Test Setup & Run Guide

This guide separates:

- ✅ One-time setup (run once)
- 🔁 Daily usage (run every time)

---

# ✅ ONE-TIME SETUP

## 1. Check Docker

<pre> ```
docker --version
docker compose version
``` </pre>

---

## 2. Install Python environment (Pipenv)

pipenv install --dev

---

## 3. Install Node (NVM)

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

export NVM_DIR="$HOME/.nvm"

source "$NVM_DIR/nvm.sh"

nvm --version

nvm install 18

nvm use 18

---

## 4. Install frontend dependencies

npm install -g gulp-cli

npm install

---

## 5. Install testing tools (for STaD)

pipenv install --dev pytest pytest-django pytest-cov mutmut

---

## 6. Set Django settings

export DJANGO_SETTINGS_MODULE=babybuddy.settings.development

(Optional: add this to ~/.zshrc so you don’t repeat it)

---

## 7. Initialize database

pipenv run python manage.py migrate

---

## 8. Run application (optional check)

gulp migrate

gulp

Open:
http://127.0.0.1:8000

Login:
admin / admin

---

# 🔁 RUN EVERY TIME (TESTING)

## Run all tests

pipenv run pytest stad_test

---

## Run specific test groups

### Black-box tests

pipenv run pytest stad_test/blackbox

### White-box tests

pipenv run pytest stad_test/whitebox

---

## Run with coverage

pipenv run pytest stad_test --cov=api --cov-branch --cov-report=term-missing

---

## Run mutation testing

pipenv run mutmut run

pipenv run mutmut results

---

# ❌ DO NOT RUN EVERY TIME

Only run these again if something breaks:

pipenv install --dev

npm install

nvm install

pipenv run python manage.py migrate

---

# ⚠️ COMMON ISSUES

## 1. Django not found

Wrong:
pytest stad_test

Correct:
pipenv run pytest stad_test

---

## 2. Wrong settings module

export DJANGO_SETTINGS_MODULE=babybuddy.settings.development

---

## 3. Database errors

pipenv run python manage.py migrate

---

## 4. Import errors

Make sure you run commands from the project root (where manage.py is located)

---

# 🚀 OPTIONAL (QUALITY OF LIFE)

Add this to ~/.zshrc:

alias pt="export DJANGO_SETTINGS_MODULE=babybuddy.settings.development && pipenv run pytest stad_test"

Then just run:
pt

---

# 🧠 SUMMARY

| Task             | Command                       |
| ---------------- | ----------------------------- |
| First-time setup | pipenv install --dev          |
| Run tests        | pipenv run pytest stad_test   |
| Coverage         | pytest --cov=api --cov-branch |
| Mutation         | mutmut run                    |
