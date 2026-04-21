"""One-off cleanup: archive legacy Notion rows with Cafeteria='科学'.

The science cafeteria was split into science_student / science_faculty, so the
old select value '科学' no longer matches what the pipeline writes. Running
the pipeline again would leave these 10 orphan rows in the database — archive
them now so the DB reflects only current state.

Delete this script (and its workflow) after running once.
"""

import os
import sys

import httpx

# 10 legacy page IDs collected via notion-search (Cafeteria='科学', all 5 days
# × 2 meals × 1 week). Run once then delete this file.
LEGACY_SCIENCE_IDS: list[str] = [
    "3490ee00-39a1-818e-b888-cb769156b8f5",  # 04-20 Mon 午餐
    "3490ee00-39a1-81ca-98f6-cb7fcf463909",  # 04-20 Mon 晚餐
    "3490ee00-39a1-81c5-8167-c8ad4a5019d6",  # 04-21 Tue 午餐
    "3490ee00-39a1-81de-a9b0-c187669849be",  # 04-21 Tue 晚餐
    "3490ee00-39a1-81e0-9781-e718db02e60f",  # 04-22 Wed 午餐
    "3490ee00-39a1-8193-8f63-ce72e7a68ebc",  # 04-22 Wed 晚餐
    "3490ee00-39a1-81b8-a9db-e579c9609fe6",  # 04-23 Thu 午餐
    "3490ee00-39a1-81ce-8588-fc03102f61df",  # 04-23 Thu 晚餐
    "3490ee00-39a1-8142-96d1-d49395752ac3",  # 04-24 Fri 午餐
    "3490ee00-39a1-8142-aa9d-e2a26abfe069",  # 04-24 Fri 晚餐
]


def main() -> int:
    token = os.environ["NOTION_TOKEN"]
    client = httpx.Client(
        timeout=30.0,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
    )
    ok = fail = 0
    for pid in LEGACY_SCIENCE_IDS:
        r = client.patch(
            f"https://api.notion.com/v1/pages/{pid}",
            json={"archived": True},
        )
        if r.status_code == 200:
            ok += 1
            print(f"archived {pid}")
        else:
            fail += 1
            print(f"failed {pid} → {r.status_code}: {r.text[:200]}")
    print(f"done: archived={ok} failed={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
