from mission_app.models import TaskType
from mission_app.storage import MissionStore


def test_parent_progress_recalculates_from_children(tmp_path):
    store = MissionStore(tmp_path / "mission.db")
    parent = store.create_task("parent", task_type=TaskType.PROJECT, estimated_minutes=40)
    child_a = store.create_task("a", parent_id=parent, estimated_minutes=20)
    child_b = store.create_task("b", parent_id=parent, estimated_minutes=60)
    store.update_task_progress(child_a, 100)
    store.update_task_progress(child_b, 0)
    row = store.row("SELECT progress FROM tasks WHERE id = ?", (parent,))
    assert row is not None
    assert row["progress"] == 25
    store.close()


def test_card_csv_roundtrip(tmp_path):
    store = MissionStore(tmp_path / "mission.db")
    deck = store.row("SELECT id FROM decks ORDER BY id LIMIT 1")
    store.create_card(deck["id"], "front", "back", tags="tag")
    csv_path = tmp_path / "cards.csv"
    store.export_cards_csv(csv_path)
    assert "front" in csv_path.read_text(encoding="utf-8")
    imported = store.import_cards_csv(csv_path)
    assert imported >= 1
    store.close()


def test_card_apkg_roundtrip(tmp_path):
    source = MissionStore(tmp_path / "source.db")
    deck = source.row("SELECT id FROM decks ORDER BY id LIMIT 1")
    source.create_card(deck["id"], "apkg front", "apkg back", tags="anki")
    apkg_path = tmp_path / "cards.apkg"
    source.export_cards_apkg(apkg_path)
    assert apkg_path.exists()
    source.close()

    target = MissionStore(tmp_path / "target.db")
    imported = target.import_cards_apkg(apkg_path)
    assert imported >= 1
    row = target.row("SELECT front, back FROM memory_cards WHERE front = ?", ("apkg front",))
    assert row is not None
    assert row["back"] == "apkg back"
    target.close()
