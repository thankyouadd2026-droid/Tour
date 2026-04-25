# Busan Trip Streamlit Implementation Plan

> **For the Agent:** Execute this plan in the current session with the requested Hotfix Track: Plan -> Change -> Verify -> Report. Do not apply the full spec-driven workflow.

**Goal:** Build a simple Streamlit app for a 1-night, 2-day Busan trip that can be used immediately and deployed to Streamlit Community Cloud.

**Architecture:** Keep all default trip data in a static JSON file and let Streamlit manage custom edits in `st.session_state`. Use `folium` and `streamlit-folium` for a no-API-key map so the app is safe for a public GitHub repository.

**Tech Stack:** Python, Streamlit, pandas, folium, streamlit-folium, static JSON.

---

### Task 1: Consolidate Reference Data

**Files:**
- Read: `docs/ref/1.json` through `docs/ref/10.json`
- Create: `data/busan_trip_data.json`

**Steps:**
1. Extract repeated places, categories, addresses, notes, and coordinates from the 10 Gemini JSON files.
2. Remove public-repo-sensitive details such as phone numbers, reservation numbers, and private addresses.
3. Create three default plans:
   - `마린시티 여유 산책 코스`
   - `남포·해운대 맛집 픽업 코스`
   - `해운대·기장 오션뷰 관광 코스`
4. Add nearby recommendations for key destinations.
5. Verify the JSON parses with `python -m json.tool data/busan_trip_data.json`.

### Task 2: Build the Streamlit App

**Files:**
- Create: `streamlit_app.py`

**Steps:**
1. Load `data/busan_trip_data.json`.
2. Let the user choose a default plan and reset the working plan from it.
3. Store the editable plan in `st.session_state`.
4. Show Day 1 and Day 2 schedules with place, category, area/address, visit time, and memo.
5. Support place add, edit, and delete using a quick-add form, delete selector, and editable schedule table.
6. Show nearby recommendations under expandable sections.
7. Render all valid coordinates on a Folium map with day-colored route lines.
8. Add a JSON download button for the current session plan.

### Task 3: Add Deployment Requirements

**Files:**
- Create: `requirements.txt`

**Steps:**
1. Add Streamlit and map dependencies.
2. Keep dependencies minimal for Streamlit Community Cloud.

### Task 4: Verify

**Commands:**
```powershell
python -m json.tool data/busan_trip_data.json > $null
python -m py_compile streamlit_app.py
```

**Manual run:**
```powershell
streamlit run streamlit_app.py
```

**Expected result:** The app opens with three selectable Busan plans, editable Day 1/Day 2 tables, nearby recommendations, and a map.
