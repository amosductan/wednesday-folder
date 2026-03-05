"""
Build the Wednesday Folder website by injecting events data into the HTML template.
Usage: python build_site.py
"""
import json
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
events_path = os.path.join(script_dir, "data", "events.json")
template_path = os.path.join(script_dir, "index.html")

# Read events data
with open(events_path, 'r', encoding='utf-8') as f:
    events_data = json.load(f)

# Read template
with open(template_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Inject data
json_str = json.dumps(events_data, ensure_ascii=False)
html = html.replace('EVENTS_DATA_PLACEHOLDER', json_str)

# Write output
output_dir = os.path.join(script_dir, "docs")
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "index.html")

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Built site: {output_path}")
print(f"Events: {sum(len(w['events']) for w in events_data['weeks'])} total across {len(events_data['weeks'])} week(s)")
