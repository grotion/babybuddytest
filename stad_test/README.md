# Baby Buddy + STaD Test Setup & Run Guide

This guide separates:

- ✅ One-time setup (run once)
- 🔁 Daily usage (run every time)

---

# ✅ ONE-TIME SETUP

## 1. Install Python environment (Pipenv)

<pre>
pipenv install --dev
</pre>

---

## 2. Install Node (NVM)

<pre>
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"
nvm --version
nvm install 18
nvm use 18
</pre>

---

## 3. Install frontend dependencies

<pre>
npm install -g gulp-cli
npm install
</pre>

---

## 4. Install testing tools (for STaD)

<pre>
pipenv install --dev pytest pytest-django pytest-cov mutmut
</pre>

---


## 5. Set Django settings

<pre>
export DJANGO_SETTINGS_MODULE=babybuddy.settings.development
</pre>

---

## (Optional) 6. Run application 

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

## Before running
<pre>
export DJANGO_SETTINGS_MODULE=babybuddy.settings.development
</pre>

## Run all tests

<pre>
pipenv run pytest stad_test
</pre>

---

## Run specific test groups

### Blackbox + Whitbox tests

<pre>
# api
pipenv run pytest stad_test/api

# babybuddy
pipenv run pytest stad_test/babybuddy

# core
pipenv run pytest stad_test/core

# dashboard
pipenv run pytest stad_test/dashboard
</pre>

### Blackbox tests

<pre>
# api
pipenv run pytest stad_test/api/api_blackbox_test.py

# babybuddy
pipenv run pytest stad_test/babybuddy/babybuddy_blackbox_test.py

# core
pipenv run pytest stad_test/core/core_blackbox_test.py

# dashboard
pipenv run pytest stad_test/dashboard/dashboard_blackbox_test.py
</pre>

### Whitebox tests

<pre>
# api
pipenv run pytest stad_test/api/api_whitebox_test.py

# babybuddy
pipenv run pytest stad_test/babybuddy/babybuddy_whitebox_test.py

# core
pipenv run pytest stad_test/core/core_whitebox_test.py

# dashboard
pipenv run pytest stad_test/dashboard/dashboard_whitebox_test.py
</pre>

---

## Run with coverage

<pre>
# api
pipenv run pytest stad_test/api/api_whitebox_test.py --cov=api --cov-branch --cov-report=html:stad_test/report/api_cov

# babybuddy
pipenv run pytest stad_test/babybuddy/babybuddy_whitebox_test.py --cov=babybuddy --cov-branch --cov-report=html:stad_test/report/babybuddy_cov

# core
pipenv run pytest stad_test/core/core_whitebox_test.py --cov=core --cov-branch --cov-report=html:stad_test/report/core_cov

# dashboard
pipenv run pytest stad_test/dashboard/dashboard_whitebox_test.py --cov=dashboard --cov-branch --cov-report=html:stad_test/report/dashboard_cov
</pre>

---

## Run mutation testing

<pre>
# api
cp stad_test/api/setup.cfg .

# babybuddy
cp stad_test/babybuddy/setup.cfg .

# core
cp stad_test/core/setup.cfg .

# dashboard
cp stad_test/dashboard/setup.cfg .

# Copy the correct config above then run these
pipenv run mutmut run
pipenv run mutmut results
</pre>
