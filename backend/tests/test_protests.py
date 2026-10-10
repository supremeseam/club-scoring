from io import BytesIO

import pytest
from django.test import Client
from pypdf import PdfReader

from racing.models import Finish, Protest
from tests.test_payments import build, editor, send

pytestmark = pytest.mark.django_db


def finish_start(race):
    return race.starts.first()


def test_penalty_reason_is_saved_and_public():
    ser, boats, races = build(require_payment=False)
    c = editor()
    st = finish_start(races[0])
    r = send(c, "put", f"/api/manage/starts/{st.id}/finishes", [
        {"boat_id": boats["B"].id, "finish_time": "2027-06-01T19:02:00", "status": "SCP", "penalty_pct": 20,
         "note": "Scoring Penalty (RRS 44.3) after contact with a mark"},
        {"boat_id": boats["C"].id, "status": "DSQ", "note": "RRS 10, protest upheld"}])
    assert r.status_code == 200, r.content
    assert {x["boat_id"]: x["note"] for x in r.json()}[boats["C"].id] == "RRS 10, protest upheld"
    pub = Client().get(f"/api/races/{races[0].id}/results").json()["fleets"][0]["rows"]
    notes = {row["boat"]["name"]: (row["code"], row["note"]) for row in pub}
    assert notes["C"] == ("DSQ", "RRS 10, protest upheld")
    assert notes["B"][0] == "SCP" and "RRS 44.3" in notes["B"][1]
    hist = Client().get(f"/api/boats/{boats['C'].id}/history").json()["rows"]
    assert any(h["note"] == "RRS 10, protest upheld" and h["status"] == "DSQ" for h in hist)


def test_standard_scoring_penalty_applies():
    ser, boats, races = build(require_payment=False)
    c = editor()
    st = finish_start(races[0])
    send(c, "put", f"/api/manage/starts/{st.id}/finishes", [
        {"boat_id": boats["A"].id, "finish_time": "2027-06-01T19:00:00", "status": "SCP", "penalty_pct": 20,
         "note": "SCP"}])
    rows = {r["boat"]["name"]: r for r in Client().get(f"/api/races/{races[0].id}/results").json()["fleets"][0]["rows"]}
    assert rows["A"]["points"] == 2          # 1st place + 20% of 4 boats, rounded = +1


def test_reason_appears_on_the_printed_sheet():
    ser, boats, races = build(require_payment=False)
    c = editor()
    st = finish_start(races[0])
    send(c, "put", f"/api/manage/starts/{st.id}/finishes", [
        {"boat_id": boats["B"].id, "status": "DSQ", "note": "RRS 42 propulsion"}])
    pdf = Client().get(f"/api/races/{races[0].id}/podium.pdf").content
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    assert "RRS 42 propulsion" in text


def test_protest_log_is_editor_only_and_public_sees_only_pending():
    ser, boats, races = build(require_payment=False)
    c = editor()
    r = send(c, "post", f"/api/manage/races/{races[0].id}/protests", {
        "protestor_id": boats["A"].id, "protestee_ids": [boats["B"].id], "rules": "RRS 10", "status": "filed"})
    assert r.status_code == 200, r.content
    pid = r.json()["id"]
    assert r.json()["protestor"] == "A" and r.json()["protestees"] == ["B"]
    assert len(c.get(f"/api/manage/races/{races[0].id}/protests").json()) == 1
    assert Client().get(f"/api/manage/races/{races[0].id}/protests").status_code == 401

    pub = Client()
    body = pub.get(f"/api/races/{races[0].id}/results").content.decode()
    assert pub.get(f"/api/races/{races[0].id}/results").json()["protests_pending"] == 1
    assert "RRS 10" not in body and "protestor" not in body        # who/what stays private

    send(c, "put", f"/api/manage/protests/{pid}", {
        "protestor_id": boats["A"].id, "protestee_ids": [boats["B"].id], "rules": "RRS 10",
        "status": "decided", "decision": "Protest upheld; B disqualified"})
    assert pub.get(f"/api/races/{races[0].id}/results").json()["protests_pending"] == 0
    assert "disqualified" not in pub.get(f"/api/races/{races[0].id}/results").content.decode()


def test_cannot_mark_results_final_while_a_protest_is_pending():
    ser, boats, races = build(require_payment=False)
    c = editor()
    pid = send(c, "post", f"/api/manage/races/{races[0].id}/protests", {"rules": "RRS 14"}).json()["id"]
    body = {"date": "2027-06-01", "status": "sailed", "results_final": True}
    assert send(c, "put", f"/api/manage/races/{races[0].id}", body).status_code == 422
    send(c, "put", f"/api/manage/protests/{pid}", {"rules": "RRS 14", "status": "withdrawn"})
    assert send(c, "put", f"/api/manage/races/{races[0].id}", body).status_code == 200


def test_protest_edits_are_audited_and_delete_works():
    ser, boats, races = build(require_payment=False)
    c = editor()
    pid = send(c, "post", f"/api/manage/races/{races[0].id}/protests", {"rules": "RRS 12"}).json()["id"]
    send(c, "put", f"/api/manage/protests/{pid}", {"rules": "RRS 12", "status": "heard"})
    assert Protest.objects.get(pk=pid).history.count() == 2          # created + updated
    assert send(c, "delete", f"/api/manage/protests/{pid}").status_code == 200
    assert not Protest.objects.filter(pk=pid).exists()
    assert Finish.objects.exists()
