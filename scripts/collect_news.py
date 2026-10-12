import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

SOURCES = [
    {
        "name": "山口県公式サイト",
        "url": "https://www.pref.yamaguchi.lg.jp/",
        "category": "official"
    },
    {
        "name": "山口市公式サイト",
        "url": "https://www.city.yamaguchi.lg.jp/",
        "category": "official"
    }
]

def check_source(source):
    result = {
        "name": source["name"],
        "url": source["url"],
        "category": source["category"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "unknown",
        "note": ""
    }

    request = Request(
        source["url"],
        headers={"User-Agent": "YamaguchiLocalUpdateBot/1.0"}
    )

    try:
        with urlopen(request, timeout=15) as response:
            result["status"] = (
                "reachable" if response.status == 200 else "check_needed"
            )
            result["note"] = f"HTTP {response.status}"
    except (URLError, HTTPError, TimeoutError) as error:
        result["status"] = "check_needed"
        result["note"] = str(error)[:200]

    return result

def main():
    os.makedirs("data", exist_ok=True)

    results = [check_source(source) for source in SOURCES]

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "公式情報源への接続確認。新店・閉店情報の抽出は未実装。",
        "sources": results
    }

    with open("data/source_checks.json", "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    for item in results:
        print(f'{item["name"]}: {item["status"]} - {item["note"]}')

if __name__ == "__main__":
    main()
