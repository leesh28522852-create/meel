from __future__ import annotations

import json
from datetime import date

import streamlit as st
from supabase import Client, create_client

# ------------------------------------------------------------
# 우리집 식단·장보기 도우미 — Supabase 공유 DB 버전
# Streamlit Secrets에 SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY 설정 필요
# ------------------------------------------------------------

MEAL_TYPES = ["아침", "점심", "저녁", "간식"]
LOCATIONS = ["냉장고", "냉동고"]

st.set_page_config(page_title="우리집 식단·장보기", page_icon="🍲", layout="wide")
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Nanum Gothic', sans-serif; }
  .block-container { max-width: 1120px; padding-top: 1.7rem; padding-bottom: 3rem; }
  h1, h2, h3 { color: #314b3c; }
  [data-testid="stMetric"] { background: #f3f7f1; border: 1px solid #e4ecdf; padding: 14px; border-radius: 14px; }
  div.stButton > button { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_db() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_PUBLISHABLE_KEY"]
    return create_client(url, key)


def fetch(table: str, order: str | None = None, descending: bool = False, limit: int | None = None):
    q = get_db().table(table).select("*")
    if order:
        q = q.order(order, desc=descending)
    if limit:
        q = q.limit(limit)
    return q.execute().data or []


def insert(table: str, data: dict):
    return get_db().table(table).insert(data).execute().data


def update(table: str, data: dict, row_id: int):
    return get_db().table(table).update(data).eq("id", row_id).execute().data


def delete(table: str, row_id: int):
    return get_db().table(table).delete().eq("id", row_id).execute().data


def clean_name(value):
    return " ".join(str(value).strip().split())


def fmt_qty(value):
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def overstock(item):
    return item.get("target_qty") is not None and float(item["quantity"]) > float(item["target_qty"])


def expiry_status(item):
    if not item.get("expiry_date"):
        return ""
    try:
        days = (date.fromisoformat(item["expiry_date"][:10]) - date.today()).days
    except (ValueError, TypeError):
        return ""
    if days < 0:
        return "⚠️ 날짜 확인 필요"
    if days <= 3:
        return f"⏳ {days}일 이내"
    return ""


def inventory_list():
    return fetch("inventory", order="name")


def ideas_list():
    return fetch("menu_ideas", order="title")


def members_list():
    return [x for x in fetch("family_members", order="name") if x.get("active", True)]


def add_to_shopping(name, quantity, unit):
    name = clean_name(name)
    if not name:
        return
    db = get_db()
    existing = (db.table("shopping_list").select("id,quantity")
                .eq("name", name).eq("unit", unit).eq("checked", False).limit(1).execute().data or [])
    if existing:
        item = existing[0]
        db.table("shopping_list").update({"quantity": float(item["quantity"]) + float(quantity)}).eq("id", item["id"]).execute()
    else:
        db.table("shopping_list").insert({"name": name, "quantity": float(quantity), "unit": unit, "checked": False}).execute()


def json_list(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


# Missing Supabase configuration: show setup directions and stop cleanly.
try:
    db = get_db()
    db.table("inventory").select("id").limit(1).execute()
except Exception as exc:
    st.title("🍲 우리집 식단·장보기")
    st.error("공유 데이터베이스에 연결하지 못했어요. Supabase 설정을 확인해 주세요.")
    st.markdown("""
**설정 순서**
1. Supabase에서 프로젝트를 만들고 `setup_supabase.sql` 내용을 SQL Editor에서 한 번 실행합니다.
2. Streamlit 앱의 **Settings → Secrets**에 아래 값을 추가합니다.
3. 앱을 재시작합니다.

```toml
SUPABASE_URL = "https://프로젝트주소.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "프로젝트의 publishable key (sb_publishable_...)"
```

접속 정보는 GitHub 코드에 넣지 마세요. 오류 세부정보: `""" + str(exc)[:500] + "`")
    st.stop()

st.title("🍲 우리집 식단·장보기")
st.caption("냉장고와 냉동고 재료를 확인하고, 가족 식사와 장보기를 함께 정리해요.")
page = st.radio("메뉴", ["오늘 한눈에", "냉장고·냉동고", "식사 일정", "메뉴와 평가", "장보기", "가족 설정"], horizontal=True, label_visibility="collapsed")

inventory = inventory_list()
ideas = ideas_list()
members = members_list()

if page == "오늘 한눈에":
    today = date.today().isoformat()
    today_plans = [p for p in fetch("meal_plans", order="meal_type") if p["meal_date"] == today]
    open_shopping = len([x for x in fetch("shopping_list") if not x.get("checked", False)])
    fridge_count = sum(1 for item in inventory if item["location"] == "냉장고")
    freezer_count = sum(1 for item in inventory if item["location"] == "냉동고")
    c1, c2, c3 = st.columns(3)
    c1.metric("냉장고 재료", f"{fridge_count}종")
    c2.metric("냉동고 재료", f"{freezer_count}종")
    c3.metric("장보기 목록", f"{open_shopping}개")

    st.subheader("오늘 함께 먹을 식사")
    order = {name: i for i, name in enumerate(MEAL_TYPES)}
    today_plans.sort(key=lambda x: order.get(x["meal_type"], 9))
    if today_plans:
        for meal in today_plans:
            people = ", ".join(json_list(meal.get("attendees"))) or "가족"
            st.info(f"**{meal['meal_type']} · {meal['menu_title']}** — 함께 먹는 사람: {people}" + (f" · {meal['note']}" if meal.get("note") else ""))
    else:
        st.write("오늘 등록된 식사 일정이 없어요. 식사 일정에서 가족이 함께 먹을 끼니를 정해보세요.")

    st.subheader("재고 확인 알림")
    excess = [item for item in inventory if overstock(item)]
    expiring = [item for item in inventory if expiry_status(item)]
    if not excess and not expiring:
        st.success("적정 수량 초과 또는 날짜 확인이 필요한 재료가 없어요.")
    for item in excess:
        st.warning(f"{item['name']} — 현재 {fmt_qty(item['quantity'])}{item['unit']}, 가족 기준 {fmt_qty(item['target_qty'])}{item['unit']}보다 많아요.")
    for item in expiring:
        st.info(f"{item['name']} ({item['location']}) — {expiry_status(item)} · {item['expiry_date']}")

    upcoming = [p for p in fetch("meal_plans", order="meal_date") if p["meal_date"] >= today][:5]
    st.subheader("다가오는 가족 식사")
    if upcoming:
        for meal in upcoming:
            people = ", ".join(json_list(meal.get("attendees"))) or "가족"
            st.write(f"**{meal['meal_date']} · {meal['meal_type']}** — {meal['menu_title']} ({people})")
    else:
        st.caption("아직 예정된 식사가 없어요.")

elif page == "냉장고·냉동고":
    st.subheader("재료 등록")
    st.caption("정확한 무게 대신 가족이 익숙한 단위로 적어도 괜찮아요. 적정 수량은 가족이 정한 기준이에요.")
    with st.form("inventory_add", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        name = c1.text_input("재료 이름", placeholder="예: 아이스크림, 달걀, 냉동만두")
        location = c2.selectbox("보관 장소", LOCATIONS)
        unit = c3.text_input("수량 단위", value="개", help="예: 개, 봉, 통, 팩")
        c4, c5, c6 = st.columns([1, 1, 1])
        quantity = c4.number_input("현재 수량", min_value=0.0, value=1.0, step=1.0)
        target = c5.number_input("가족 적정 수량", min_value=0.0, value=0.0, step=1.0, help="0이면 기준을 설정하지 않아요.")
        has_expiry = c6.checkbox("유통기한 입력")
        expiry = c6.date_input("유통기한", value=date.today(), format="YYYY-MM-DD") if has_expiry else None
        submitted = st.form_submit_button("재료 추가", use_container_width=True)
    if submitted:
        name = clean_name(name)
        unit = clean_name(unit) or "개"
        if not name:
            st.error("재료 이름을 적어주세요.")
        else:
            insert("inventory", {"name": name, "location": location, "quantity": quantity, "unit": unit,
                                  "target_qty": target if target > 0 else None,
                                  "expiry_date": expiry.isoformat() if expiry else None})
            st.success(f"{name}을(를) {location} 목록에 추가했어요.")
            st.rerun()

    st.divider()
    floc = st.selectbox("재료 보기", ["모두 보기", *LOCATIONS], key="inventory_filter")
    shown = [i for i in inventory if floc == "모두 보기" or i["location"] == floc]
    if not shown:
        st.info("등록된 재료가 없어요. 위에서 먼저 추가해보세요.")
    for item in shown:
        with st.container(border=True):
            top1, top2 = st.columns([3, 2])
            with top1:
                st.markdown(f"**{item['name']}** · {item['location']}")
                detail = f"현재 {fmt_qty(item['quantity'])}{item['unit']}"
                if item.get("target_qty") is not None:
                    detail += f" · 가족 적정 수량 {fmt_qty(item['target_qty'])}{item['unit']}"
                if item.get("expiry_date"):
                    detail += f" · 날짜 {item['expiry_date']}"
                st.caption(detail)
                if overstock(item):
                    st.warning(f"적정 수량보다 {fmt_qty(float(item['quantity'])-float(item['target_qty']))}{item['unit']} 많아요. 다음 장보기 전에 확인해보세요.")
                if expiry_status(item):
                    st.caption(expiry_status(item))
            with top2:
                with st.form(f"inventory_edit_{item['id']}"):
                    new_qty = st.number_input("수량 수정", min_value=0.0, value=float(item["quantity"]), step=1.0, key=f"qty_{item['id']}")
                    new_target = st.number_input("적정 수량 수정 (0=미설정)", min_value=0.0, value=float(item.get("target_qty") or 0), step=1.0, key=f"target_{item['id']}")
                    b1, b2 = st.columns(2)
                    save_item = b1.form_submit_button("수량·기준 저장")
                    remove_item = b2.form_submit_button("다 먹음/삭제")
                if save_item:
                    update("inventory", {"quantity": new_qty, "target_qty": new_target if new_target > 0 else None}, item["id"])
                    st.rerun()
                if remove_item:
                    delete("inventory", item["id"])
                    st.rerun()

elif page == "식사 일정":
    st.subheader("가족이 함께 먹을 식사 정하기")
    st.caption("날짜와 끼니를 먼저 정하고, 메뉴는 저장된 메뉴를 고르거나 직접 입력할 수 있어요.")
    idea_titles = [r["title"] for r in ideas]
    with st.form("plan_add"):
        c1, c2, c3 = st.columns(3)
        meal_day = c1.date_input("날짜", value=date.today(), min_value=date.today())
        meal_type = c2.selectbox("끼니", MEAL_TYPES)
        menu_choice = c3.selectbox("메뉴", ["직접 입력", *idea_titles])
        custom_menu = st.text_input("메뉴 직접 입력 (저장 메뉴에서 선택했다면 비워두세요)", placeholder="예: 토마토 달걀볶음과 밥")
        people_names = [m["name"] for m in members]
        attendees = st.multiselect("함께 먹을 가족", people_names, default=people_names)
        plan_note = st.text_input("메모 (선택)", placeholder="예: 엄마 퇴근 후 저녁")
        plan_submit = st.form_submit_button("식사 일정 저장", use_container_width=True)
    if plan_submit:
        title = clean_name(custom_menu) if menu_choice == "직접 입력" or custom_menu.strip() else menu_choice
        if not title:
            st.error("메뉴를 선택하거나 입력해주세요.")
        else:
            get_db().table("meal_plans").upsert({"meal_date": meal_day.isoformat(), "meal_type": meal_type,
                "menu_title": title, "attendees": attendees, "note": clean_name(plan_note)}, on_conflict="meal_date,meal_type").execute()
            st.success("식사 일정을 저장했어요. 같은 날짜와 끼니의 일정이 있으면 새 내용으로 바뀝니다.")
            st.rerun()

    st.divider()
    st.subheader("예정된 식사 일정")
    plans = [p for p in fetch("meal_plans", order="meal_date") if p["meal_date"] >= date.today().isoformat()]
    order = {name: i for i, name in enumerate(MEAL_TYPES)}
    plans.sort(key=lambda p: (p["meal_date"], order.get(p["meal_type"], 9)))
    if not plans:
        st.info("예정된 일정이 없어요.")
    for plan in plans[:40]:
        who = ", ".join(json_list(plan.get("attendees"))) or "가족"
        col1, col2, col3 = st.columns([4, 1.5, 1])
        col1.write(f"**{plan['meal_date']} · {plan['meal_type']} — {plan['menu_title']}**  \n함께 먹는 사람: {who}" + (f" · {plan['note']}" if plan.get("note") else ""))
        if col2.button("재료 확인", key=f"plan_ingredients_{plan['id']}"):
            idea = next((x for x in ideas_list() if x["title"] == plan["menu_title"]), None)
            if not idea or not idea.get("ingredients", "").strip():
                st.info("이 메뉴에 저장된 주요 재료가 없어요. 메뉴와 평가 탭에서 재료를 등록할 수 있어요.")
            else:
                ingredients = [clean_name(x) for x in idea["ingredients"].split(",") if clean_name(x)]
                stock_names = {x["name"].casefold() for x in inventory_list() if float(x["quantity"]) > 0}
                missing = [x for x in ingredients if x.casefold() not in stock_names]
                if not missing:
                    st.success("등록된 주요 재료가 모두 재고에 있어요.")
                else:
                    for item_name in missing:
                        add_to_shopping(item_name, 1, "필요량 확인")
                    st.success("재고에 없는 재료를 장보기 목록에 담았어요: " + ", ".join(missing) + " (구매 시 수량과 단위를 확인해 주세요.)")
                    st.rerun()
        if col3.button("일정 삭제", key=f"delete_plan_{plan['id']}"):
            delete("meal_plans", plan["id"])
            st.rerun()

elif page == "메뉴와 평가":
    st.subheader("가족 메뉴 모음")
    st.caption("자주 먹고 싶은 메뉴를 저장해두면 식사 일정에 빠르게 추가할 수 있어요.")
    with st.form("idea_add", clear_on_submit=True):
        idea_title = st.text_input("메뉴 이름", placeholder="예: 불고기")
        idea_ingredients = st.text_input("주요 재료 (쉼표로 구분)", placeholder="예: 소고기, 양파, 당근")
        idea_note = st.text_input("메모 (선택)", placeholder="예: 맵지 않게")
        idea_submit = st.form_submit_button("메뉴 저장")
    if idea_submit:
        idea_title = clean_name(idea_title)
        if not idea_title:
            st.error("메뉴 이름을 입력해주세요.")
        else:
            try:
                insert("menu_ideas", {"title": idea_title, "ingredients": clean_name(idea_ingredients), "note": clean_name(idea_note)})
                st.success("메뉴를 저장했어요.")
                st.rerun()
            except Exception:
                st.warning("저장하지 못했어요. 메뉴 이름이 이미 있거나 데이터베이스 설정을 확인해야 할 수 있어요.")

    ideas = ideas_list()
    if ideas:
        with st.expander("저장된 메뉴 보기", expanded=True):
            for idea in ideas:
                ingredients = f" · 주요 재료: {idea['ingredients']}" if idea.get("ingredients") else ""
                st.write(f"**{idea['title']}**{ingredients}" + (f" · {idea['note']}" if idea.get("note") else ""))

    st.divider()
    st.subheader("먹은 메뉴 평가")
    st.caption("메뉴는 좋음/보통으로 평가하고, 다시 먹을지와 다음에 다시 살 재료를 기록해요.")
    all_titles = sorted(set([r["title"] for r in ideas_list()] + [r["menu_title"] for r in fetch("meal_plans")]), key=str.casefold)
    with st.form("rate_meal", clear_on_submit=True):
        eaten_date = st.date_input("먹은 날짜", value=date.today(), key="rating_date")
        rated_menu = st.selectbox("메뉴", ["직접 입력", *all_titles])
        custom_rated_menu = st.text_input("직접 입력할 메뉴명", placeholder="예: 버섯 크림 파스타")
        rating = st.radio("어땠나요?", ["좋음", "보통"], horizontal=True)
        repeat_menu = st.checkbox("다음 식단에도 이 메뉴 넣기")
        ingredient_names = sorted(set([r["name"] for r in inventory_list()]), key=str.casefold)
        buy_again = st.multiselect("다음에 다시 사고 싶은 재료 (선택)", ingredient_names)
        buy_again_other = st.text_input("목록에 없는 재료도 추가 (쉼표로 구분)", placeholder="예: 두부, 대파")
        rating_note = st.text_input("한 줄 메모 (선택)", placeholder="예: 양이 적당했어요")
        rating_submit = st.form_submit_button("평가 저장", use_container_width=True)
    if rating_submit:
        title = clean_name(custom_rated_menu) if rated_menu == "직접 입력" or custom_rated_menu.strip() else rated_menu
        if not title:
            st.error("메뉴를 선택하거나 입력해주세요.")
        else:
            buy_list = list(dict.fromkeys(buy_again + [clean_name(x) for x in buy_again_other.split(",") if clean_name(x)]))
            insert("meal_ratings", {"eaten_date": eaten_date.isoformat(), "menu_title": title, "rating": rating,
                "repeat_menu": repeat_menu, "buy_again": buy_list, "note": clean_name(rating_note)})
            st.success("평가를 저장했어요.")
            st.rerun()

    ratings = fetch("meal_ratings", order="eaten_date", descending=True, limit=30)
    if ratings:
        st.divider()
        st.subheader("최근 식사 평가")
        for r in ratings:
            details = [r["rating"]]
            if r.get("repeat_menu"):
                details.append("다음 식단에 다시 넣기")
            if json_list(r.get("buy_again")):
                details.append("다시 살 재료: " + ", ".join(json_list(r["buy_again"])))
            if r.get("note"):
                details.append(r["note"])
            st.write(f"**{r['eaten_date']} · {r['menu_title']}** — " + " · ".join(details))

elif page == "장보기":
    st.subheader("장보기 목록")
    st.caption("재고에 이미 있는 품목이나 적정 수량 초과 품목은 추가 전에 알려드려요. 구매 여부는 가족이 결정합니다.")
    with st.form("shopping_add", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        shop_name = c1.text_input("살 재료", placeholder="예: 우유")
        shop_qty = c2.number_input("수량", min_value=0.1, value=1.0, step=1.0)
        shop_unit = c3.text_input("단위", value="개")
        shop_submit = st.form_submit_button("목록에 추가")
    if shop_submit:
        shop_name = clean_name(shop_name)
        if not shop_name:
            st.error("재료 이름을 입력해주세요.")
        else:
            matches = [i for i in inventory_list() if i["name"].casefold() == shop_name.casefold()]
            for item in matches:
                if overstock(item):
                    st.warning(f"확인: {item['location']}에 {fmt_qty(item['quantity'])}{item['unit']} 있고 가족 기준은 {fmt_qty(item['target_qty'])}{item['unit']}예요.")
                else:
                    st.info(f"참고: {item['location']}에 {fmt_qty(item['quantity'])}{item['unit']} 있어요.")
            add_to_shopping(shop_name, shop_qty, clean_name(shop_unit) or "개")
            st.success("장보기 목록에 추가했어요. 구매 전에 재고를 한 번 확인해보세요.")
            st.rerun()

    shopping = fetch("shopping_list", order="id")
    open_items = [i for i in shopping if not i.get("checked", False)]
    st.markdown("#### 살 것")
    if not open_items:
        st.info("장보기 목록이 비어 있어요.")
    for item in open_items:
        c1, c2, c3 = st.columns([4, 2, 1])
        c1.write(f"**{item['name']}** · {fmt_qty(item['quantity'])}{item['unit']}")
        with c2:
            with st.form(f"bought_{item['id']}"):
                bought_location = st.selectbox("구매 후 보관", LOCATIONS, key=f"loc_{item['id']}")
                bought_qty = st.number_input("구매 수량", min_value=0.1, value=float(item["quantity"]), step=1.0, key=f"bqty_{item['id']}")
                bought_unit = st.text_input("단위 확인/수정", value=item["unit"], key=f"bunit_{item['id']}")
                bought = st.form_submit_button("구매 완료·재고 추가")
            if bought:
                insert("inventory", {"name": item["name"], "location": bought_location, "quantity": bought_qty, "unit": clean_name(bought_unit) or "개"})
                update("shopping_list", {"checked": True}, item["id"])
                st.rerun()
        if c3.button("삭제", key=f"shop_delete_{item['id']}"):
            delete("shopping_list", item["id"])
            st.rerun()

    done = [i for i in shopping if i.get("checked", False)]
    if done:
        with st.expander("최근 구매 완료 항목"):
            for item in done[-20:][::-1]:
                st.write(f"✅ {item['name']} · {fmt_qty(item['quantity'])}{item['unit']}")
                if st.button("완료 목록에서 지우기", key=f"done_delete_{item['id']}"):
                    delete("shopping_list", item["id"])
                    st.rerun()

elif page == "가족 설정":
    st.subheader("가족 구성원")
    st.caption("식사 일정에서 함께 먹을 사람을 선택할 수 있어요.")
    with st.form("member_add", clear_on_submit=True):
        member_name = st.text_input("가족 이름", placeholder="예: 엄마")
        member_submit = st.form_submit_button("가족 추가")
    if member_submit:
        member_name = clean_name(member_name)
        if not member_name:
            st.error("이름을 입력해주세요.")
        else:
            try:
                insert("family_members", {"name": member_name, "active": True})
                st.success("가족을 추가했어요.")
                st.rerun()
            except Exception:
                st.warning("추가하지 못했어요. 이미 등록된 이름인지 확인해 주세요.")
    for member in members_list():
        c1, c2 = st.columns([5, 1])
        c1.write(f"👤 {member['name']}")
        if c2.button("삭제", key=f"member_del_{member['id']}"):
            update("family_members", {"active": False}, member["id"])
            st.rerun()

    st.divider()
    st.subheader("가족 적정 수량")
    st.write("재료 목록에서 각 품목의 가족 적정 수량을 정할 수 있어요. 기준을 넘으면 알림만 보여주며, 구매를 막지는 않습니다.")
    st.caption("예: 아이스크림 2통, 냉동만두 2봉처럼 가족끼리 기준을 정해보세요.")

st.divider()
st.caption("※ 재고와 날짜는 직접 입력한 정보입니다. 식품 안전 여부를 판정하지 않으므로 포장지의 보관·유통기한 안내를 확인하세요.")
st.caption("공유 데이터베이스를 사용합니다. 앱 링크를 가진 사람은 가족 데이터의 조회·추가·수정·삭제가 가능합니다.")
