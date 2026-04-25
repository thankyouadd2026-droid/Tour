from __future__ import annotations

import copy
import json
import math
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium


DATA_PATH = Path(__file__).parent / "data" / "busan_trip_data.json"
EDITABLE_COLUMNS = ["time", "place", "category", "area", "address", "memo", "lat", "lon"]


@st.cache_data
def load_data() -> dict[str, Any]:
    with DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_plan(data: dict[str, Any], plan_id: str) -> dict[str, Any]:
    for plan in data["plans"]:
        if plan["id"] == plan_id:
            return copy.deepcopy(plan)
    return copy.deepcopy(data["plans"][0])


def ensure_state(data: dict[str, Any]) -> None:
    if "selected_plan_id" not in st.session_state:
        st.session_state.selected_plan_id = data["plans"][0]["id"]
    if "working_plan" not in st.session_state:
        st.session_state.working_plan = get_plan(data, st.session_state.selected_plan_id)
    if "edit_version" not in st.session_state:
        st.session_state.edit_version = 0


def reset_working_plan(data: dict[str, Any], plan_id: str) -> None:
    st.session_state.selected_plan_id = plan_id
    st.session_state.working_plan = get_plan(data, plan_id)
    st.session_state.edit_version += 1


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def parse_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def valid_coordinate(lat: Any, lon: Any) -> bool:
    lat_value = parse_optional_float(lat)
    lon_value = parse_optional_float(lon)
    return lat_value is not None and lon_value is not None


def items_to_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in items:
        rows.append({column: item.get(column, "") for column in EDITABLE_COLUMNS})
    return pd.DataFrame(rows, columns=EDITABLE_COLUMNS)


def sync_day_items(day_index: int, edited: pd.DataFrame) -> None:
    day = st.session_state.working_plan["days"][day_index]
    old_items = day.get("items", [])
    new_items: list[dict[str, Any]] = []

    for row_index, row in edited.reset_index(drop=True).iterrows():
        place = clean_text(row.get("place"))
        if not place:
            continue

        old_item = old_items[row_index] if row_index < len(old_items) else {}
        new_items.append(
            {
                "id": old_item.get("id", f"custom-{uuid.uuid4().hex[:8]}"),
                "time": clean_text(row.get("time")),
                "place": place,
                "category": clean_text(row.get("category")),
                "area": clean_text(row.get("area")),
                "address": clean_text(row.get("address")),
                "memo": clean_text(row.get("memo")),
                "lat": parse_optional_float(row.get("lat")),
                "lon": parse_optional_float(row.get("lon")),
                "nearby": old_item.get("nearby", []),
            }
        )

    day["items"] = new_items


def flat_items(plan: dict[str, Any]) -> list[tuple[int, int, dict[str, Any]]]:
    rows = []
    for day_index, day in enumerate(plan.get("days", [])):
        for item_index, item in enumerate(day.get("items", [])):
            rows.append((day_index, item_index, item))
    return rows


def add_place(day_number: int, place: dict[str, Any]) -> None:
    for day in st.session_state.working_plan["days"]:
        if day["day"] == day_number:
            day["items"].append(place)
            st.session_state.edit_version += 1
            return


def plan_points(plan: dict[str, Any]) -> list[dict[str, Any]]:
    points = []
    for day in plan.get("days", []):
        for item in day.get("items", []):
            lat = parse_optional_float(item.get("lat"))
            lon = parse_optional_float(item.get("lon"))
            if lat is None or lon is None:
                continue
            points.append(
                {
                    "day": day.get("day"),
                    "time": item.get("time", ""),
                    "place": item.get("place", ""),
                    "category": item.get("category", ""),
                    "lat": lat,
                    "lon": lon,
                    "memo": item.get("memo", ""),
                }
            )
    return points


def render_map(plan: dict[str, Any]) -> None:
    points = plan_points(plan)
    if not points:
        st.info("지도에 표시할 좌표가 없습니다. 장소에 위도와 경도를 입력하면 지도에 표시됩니다.")
        return

    center = [
        sum(point["lat"] for point in points) / len(points),
        sum(point["lon"] for point in points) / len(points),
    ]
    route_map = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")
    colors = {1: "blue", 2: "green"}
    route_lines: dict[int, list[list[float]]] = {}

    for point in points:
        day = int(point["day"] or 1)
        route_lines.setdefault(day, []).append([point["lat"], point["lon"]])
        popup = folium.Popup(
            f"<strong>Day {day} · {point['time']}</strong><br>{point['place']}<br>{point['category']}",
            max_width=260,
        )
        folium.Marker(
            [point["lat"], point["lon"]],
            tooltip=f"Day {day} · {point['place']}",
            popup=popup,
            icon=folium.Icon(color=colors.get(day, "cadetblue"), icon="info-sign"),
        ).add_to(route_map)

    for day, coordinates in route_lines.items():
        if len(coordinates) >= 2:
            folium.PolyLine(
                coordinates,
                color=colors.get(day, "cadetblue"),
                weight=3,
                opacity=0.65,
                tooltip=f"Day {day} 이동 흐름",
            ).add_to(route_map)

    st_folium(route_map, height=420, returned_objects=[])


def render_nearby(plan: dict[str, Any]) -> None:
    st.subheader("목적지 주변 추천")
    for day in plan.get("days", []):
        with st.expander(f"Day {day['day']} · {day.get('title', '')}", expanded=False):
            has_nearby = False
            for item in day.get("items", []):
                nearby = item.get("nearby") or []
                if not nearby:
                    continue
                has_nearby = True
                st.markdown(f"**{item.get('time', '')} · {item.get('place', '')} 주변**")
                for recommendation in nearby:
                    st.markdown(
                        f"- **{recommendation.get('name', '')}** · "
                        f"{recommendation.get('category', '')} · "
                        f"{recommendation.get('distance', '')}  \n"
                        f"  {recommendation.get('memo', '')}"
                    )
            if not has_nearby:
                st.caption("이 Day에는 주변 추천이 아직 없습니다.")


def render_add_form(data: dict[str, Any]) -> None:
    catalog = data.get("place_catalog", [])
    catalog_by_name = {place["name"]: place for place in catalog}
    options = ["직접 입력"] + list(catalog_by_name.keys())

    with st.expander("장소 빠른 추가", expanded=False):
        selected_name = st.selectbox("추천 장소에서 불러오기", options, key="catalog_pick")
        preset = catalog_by_name.get(selected_name, {})
        preset_key = selected_name.replace(" ", "_")

        with st.form("add_place_form", clear_on_submit=True):
            day_number = st.selectbox("추가할 날", [1, 2], format_func=lambda value: f"Day {value}")
            time_value = st.text_input("방문 시간", value="", key=f"add_time_{preset_key}")
            place_value = st.text_input("장소명", value=preset.get("name", ""), key=f"add_place_{preset_key}")
            category_value = st.text_input("카테고리", value=preset.get("category", ""), key=f"add_category_{preset_key}")
            area_value = st.text_input("지역", value=preset.get("area", ""), key=f"add_area_{preset_key}")
            address_value = st.text_input("주소", value=preset.get("address", ""), key=f"add_address_{preset_key}")
            memo_value = st.text_area("메모", value=preset.get("memo", ""), height=90, key=f"add_memo_{preset_key}")
            lat_value = st.text_input("위도", value=str(preset.get("lat", "")), key=f"add_lat_{preset_key}")
            lon_value = st.text_input("경도", value=str(preset.get("lon", "")), key=f"add_lon_{preset_key}")
            submitted = st.form_submit_button("장소 추가", type="primary")

        if submitted:
            if not place_value.strip():
                st.warning("장소명을 입력해야 추가할 수 있습니다.")
                return

            add_place(
                day_number,
                {
                    "id": f"custom-{uuid.uuid4().hex[:8]}",
                    "time": time_value.strip(),
                    "place": place_value.strip(),
                    "category": category_value.strip(),
                    "area": area_value.strip(),
                    "address": address_value.strip(),
                    "memo": memo_value.strip(),
                    "lat": parse_optional_float(lat_value),
                    "lon": parse_optional_float(lon_value),
                    "nearby": [],
                },
            )
            st.success(f"'{place_value.strip()}'을(를) Day {day_number}에 추가했습니다.")
            st.rerun()


def render_delete_control() -> None:
    rows = flat_items(st.session_state.working_plan)
    if not rows:
        return

    with st.expander("장소 삭제", expanded=False):
        labels = [
            f"Day {st.session_state.working_plan['days'][day_index]['day']} · "
            f"{item.get('time', '')} · {item.get('place', '')}"
            for day_index, _, item in rows
        ]
        selected_label = st.selectbox("삭제할 장소", labels)
        selected_index = labels.index(selected_label)

        if st.button("선택 장소 삭제"):
            day_index, item_index, item = rows[selected_index]
            del st.session_state.working_plan["days"][day_index]["items"][item_index]
            st.session_state.edit_version += 1
            st.success(f"'{item.get('place', '')}'을(를) 삭제했습니다.")
            st.rerun()


def render_day_cards(day: dict[str, Any]) -> None:
    for item in day.get("items", []):
        with st.container(border=True):
            time_value = item.get("time") or "시간 미정"
            category = item.get("category") or "분류 없음"
            st.markdown(f"**{time_value}** · {category}")
            st.markdown(f"#### {item.get('place', '')}")

            area = item.get("area", "")
            address = item.get("address", "")
            if area or address:
                st.caption(" · ".join(part for part in [area, address] if part))

            memo = item.get("memo", "")
            if memo:
                st.write(memo)


def render_schedule(start_date: date) -> None:
    st.subheader("일정표")
    for day_index, day in enumerate(st.session_state.working_plan.get("days", [])):
        day_date = start_date + timedelta(days=day.get("day", 1) - 1)
        st.markdown(f"### Day {day.get('day')} · {day_date:%Y-%m-%d} · {day.get('title', '')}")
        render_day_cards(day)

        with st.expander("표로 수정하기", expanded=False):
            edited = st.data_editor(
                items_to_dataframe(day.get("items", [])),
                key=f"editor-{st.session_state.selected_plan_id}-{st.session_state.edit_version}-{day_index}",
                num_rows="dynamic",
                hide_index=True,
                use_container_width=True,
                column_config={
                    "time": st.column_config.TextColumn("방문 시간", width="small"),
                    "place": st.column_config.TextColumn("장소명", required=True, width="medium"),
                    "category": st.column_config.TextColumn("카테고리", width="small"),
                    "area": st.column_config.TextColumn("지역", width="small"),
                    "address": st.column_config.TextColumn("주소", width="medium"),
                    "memo": st.column_config.TextColumn("메모", width="large"),
                    "lat": st.column_config.NumberColumn("위도", format="%.6f", width="small"),
                    "lon": st.column_config.NumberColumn("경도", format="%.6f", width="small"),
                },
            )
            sync_day_items(day_index, edited)


def render_sidebar(data: dict[str, Any]) -> date:
    plan_options = {plan["name"]: plan["id"] for plan in data["plans"]}
    current_name = next(
        name for name, plan_id in plan_options.items() if plan_id == st.session_state.selected_plan_id
    )

    st.sidebar.header("코스 선택")
    selected_name = st.sidebar.selectbox(
        "기본 여행계획",
        list(plan_options.keys()),
        index=list(plan_options.keys()).index(current_name),
    )
    selected_plan_id = plan_options[selected_name]

    if selected_plan_id != st.session_state.selected_plan_id:
        st.sidebar.info("아래 버튼을 누르면 현재 수정 내용이 선택한 기본 코스로 바뀝니다.")

    if st.sidebar.button("선택한 코스로 시작/초기화", type="primary"):
        reset_working_plan(data, selected_plan_id)
        st.rerun()

    start_date = st.sidebar.date_input("여행 시작일", value=date.today())
    st.sidebar.divider()
    st.sidebar.download_button(
        "현재 계획 JSON 다운로드",
        data=json.dumps(st.session_state.working_plan, ensure_ascii=False, indent=2),
        file_name=f"{st.session_state.working_plan['id']}.json",
        mime="application/json",
    )
    return start_date


def apply_mobile_css() -> None:
    st.markdown(
        """
        <style>
        html, body, [class*="css"] {
            letter-spacing: 0;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
        }
        div[data-testid="stMetric"] {
            background: #f7f9fc;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            color: #111827;
            padding: 0.75rem;
        }
        div[data-testid="stMetric"] * {
            color: inherit !important;
        }
        @media (max-width: 768px) {
            .block-container {
                padding-left: 0.75rem;
                padding-right: 0.75rem;
            }
            h1 {
                font-size: 2.05rem !important;
                line-height: 1.18 !important;
                margin-bottom: 0.75rem !important;
            }
            h2 {
                font-size: 1.55rem !important;
                line-height: 1.22 !important;
                margin-top: 1rem !important;
            }
            h3 {
                font-size: 1.2rem !important;
                line-height: 1.25 !important;
            }
            h4 {
                font-size: 1.08rem !important;
                line-height: 1.25 !important;
                margin: 0.2rem 0 0.35rem 0 !important;
            }
            p, li, .stMarkdown, .stCaptionContainer {
                font-size: 0.95rem !important;
                line-height: 1.55 !important;
            }
            div[data-testid="stMetric"] {
                padding: 0.65rem 0.75rem;
            }
            div[data-testid="stMetricLabel"] {
                font-size: 0.85rem !important;
            }
            div[data-testid="stMetricValue"] {
                font-size: 1.8rem !important;
                line-height: 1.15 !important;
            }
            div[data-baseweb="tab-list"] {
                gap: 0.15rem;
                overflow-x: auto;
                scrollbar-width: none;
            }
            button[data-baseweb="tab"] {
                padding-left: 0.4rem;
                padding-right: 0.4rem;
                min-width: max-content;
            }
            div[data-testid="stDataFrame"] {
                font-size: 0.85rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="부산 1박 2일 여행 플래너",
        layout="wide",
    )
    apply_mobile_css()

    data = load_data()
    ensure_state(data)
    start_date = render_sidebar(data)
    plan = st.session_state.working_plan

    st.title(data["metadata"]["title"])
    st.caption("기본 코스를 고른 뒤 일정표를 바로 수정해 쓰는 Streamlit 여행계획 앱입니다.")

    st.markdown(f"## {plan['name']}")
    st.write(plan["description"])

    col1, col2, col3 = st.columns(3)
    col1.metric("여행 기간", "1박 2일")
    col2.metric("일정 수", f"{len(flat_items(plan))}개")
    col3.metric("지도 표시", f"{len(plan_points(plan))}곳")

    tab_schedule, tab_map, tab_nearby, tab_edit = st.tabs(
        ["일정표", "지도", "주변 추천", "추가/삭제"]
    )

    with tab_schedule:
        render_schedule(start_date)

    with tab_map:
        render_map(st.session_state.working_plan)

    with tab_nearby:
        render_nearby(st.session_state.working_plan)

    with tab_edit:
        render_add_form(data)
        render_delete_control()
        st.info("일정 수정은 '일정표' 탭의 표에서 바로 편집할 수 있습니다. 변경 내용은 현재 브라우저 세션에만 유지됩니다.")


if __name__ == "__main__":
    main()
