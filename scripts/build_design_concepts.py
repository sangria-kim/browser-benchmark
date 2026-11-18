"""Build the portable design gallery from the published benchmark events."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONCEPTS = ROOT / "dashboard" / "concepts"
KST = timezone(timedelta(hours=9))


def build_design_concepts(output):
    editorial = json.loads((CONCEPTS / "stories.json").read_text())
    catalog = json.loads((ROOT / "dashboard/catalog.json").read_text())["events"]
    stories = []
    for event_id, copy in editorial.items():
        event = json.loads((ROOT / "data/events" / f"{event_id}.json").read_text())
        scope = event["scope"]
        observed = datetime.fromisoformat(event["observed_at"].replace("Z", "+00:00")).astimezone(KST)
        sources = [s if isinstance(s, str) else s["url"] for s in event["sources"]]
        media = [item for item in catalog.get(event_id, {}).get("media", [])
                 if item["type"] in ("image", "video") and item["url"].startswith("https://")]
        stories.append({
            **copy, "id": event_id, "browser": event["browser"], "version": event["version"],
            "platform": event["platform"], "builds": scope.get("builds", {}),
            "stage": copy.get("stage") or {"stable": "정식판", "beta": "베타"}.get(event["channel"], "단계 미확인"),
            "condition": copy.get("condition") or scope.get("conditions"),
            "day": observed.date().isoformat(), "time": observed.strftime("%H:%M"),
            "issue": (observed.date() + timedelta(days=1)).isoformat(),
            "announced": event["announced_at"], "effective": event["effective_at"],
            "sources": [url for url in sources if url.startswith("https://")], "media": media,
        })
    template = (CONCEPTS / "page.html").read_text()
    # Keep source text inert inside a script element, including a literal closing tag.
    data = json.dumps(stories, ensure_ascii=False, separators=(",", ":")).replace("<", r"\u003c")
    template = template.replace("<!--STYLES-->", (CONCEPTS / "design.css").read_text())
    template = template.replace("<!--SCRIPT-->", (CONCEPTS / "design.js").read_text())
    target = output / "concepts" / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template.replace("<!--STORIES-->", data), encoding="utf-8")
    return target


if __name__ == "__main__":
    print(build_design_concepts(ROOT / "dist"))
