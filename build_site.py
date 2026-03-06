"""
Build the Ductan Kids school updates website.
Injects Maya (St. Cloud) and Isaac (SOCDS) data into the HTML template.
Usage: python build_site.py
"""
import json
import os
from pathlib import Path

script_dir = Path(__file__).parent.resolve()

# Maya data (St. Cloud events)
events_path = script_dir / "data" / "events.json"
with open(events_path, 'r', encoding='utf-8') as f:
    maya_data = json.load(f)

# Isaac data (SOCDS newsletters)
socds_data_dir = script_dir / "socds" / "data"
isaac_weeks = []
if socds_data_dir.exists():
    for f in sorted(socds_data_dir.glob("week_*.json"), reverse=True):
        with open(f, 'r', encoding='utf-8') as fh:
            isaac_weeks.append(json.load(fh))

isaac_data = {
    "school": "South Orange Country Day School",
    "class": "PreK Orange",
    "last_updated": isaac_weeks[0]["date"] if isaac_weeks else "",
    "weeks": isaac_weeks
}

# Read template
template_path = script_dir / "index.html"
with open(template_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Inject data
html = html.replace('MAYA_DATA_PLACEHOLDER', json.dumps(maya_data, ensure_ascii=False))
html = html.replace('ISAAC_DATA_PLACEHOLDER', json.dumps(isaac_data, ensure_ascii=False))

# Write output
output_dir = script_dir / "docs"
output_dir.mkdir(exist_ok=True)
output_path = output_dir / "index.html"

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

maya_events = sum(len(w['events']) for w in maya_data['weeks'])
print(f"Built site: {output_path}")
print(f"Maya (St. Cloud): {maya_events} events across {len(maya_data['weeks'])} weeks")
print(f"Isaac (SOCDS): {len(isaac_weeks)} weekly newsletters")
