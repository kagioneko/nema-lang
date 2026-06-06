"""
しーちゃん連携モジュール

spirit.db (state_snapshots) の感情データを
Nema NeuroState 6次元に変換して注入する。

しーちゃん次元 → Nema 次元マッピング:
  desire   → dp   (ドーパミン：欲求・動機)
  euphoria → e    (エンドルフィン：快楽・達成)
  calm     → gaba (GABA：冷静・抑制)
  openness → ac   (アセチルコリン：開放性・集中)
  sorrow   → s    (セロトニン逆：高悲しみ→低安定)
  guilt    → ox   (オキシトシン逆：高罪悪感→低信頼)
"""

import sqlite3
import json
from pathlib import Path

SPIRIT_DB_DEFAULT = Path.home() / "workspace/vps-spirit/data/spirit.db"


def load_latest(db_path: str | Path = SPIRIT_DB_DEFAULT) -> dict[str, float]:
    """
    spirit.db から最新の NeuroState スナップショットを読み込み、
    Nema の6次元 (dp/s/ac/ox/gaba/e) に変換して返す。
    """
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute(
        "SELECT state_json, timestamp FROM state_snapshots "
        "ORDER BY timestamp DESC LIMIT 1"
    )
    row = cur.fetchone()
    con.close()

    if not row:
        raise ValueError("spirit.db に state_snapshots データがありません")

    data = json.loads(row[0])
    timestamp = row[1]

    nema_state = {
        "dp":   _clamp(data.get("desire",   0.5)),
        "s":    _clamp(1.0 - data.get("sorrow",  0.0)),
        "ac":   _clamp(data.get("openness", 0.5)),
        "ox":   _clamp(1.0 - data.get("guilt",   0.0)),
        "gaba": _clamp(data.get("calm",     0.5)),
        "e":    _clamp(data.get("euphoria", 0.5)),
    }
    return nema_state, timestamp, data


def load_history(db_path: str | Path = SPIRIT_DB_DEFAULT,
                 limit: int = 10) -> list[dict]:
    """最近 N 件のスナップショット履歴を返す"""
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute(
        "SELECT state_json, timestamp FROM state_snapshots "
        "ORDER BY timestamp DESC LIMIT ?", (limit,)
    )
    rows = cur.fetchall()
    con.close()
    return [{"nema": _convert(json.loads(r[0])), "timestamp": r[1],
             "raw": json.loads(r[0])} for r in rows]


def _convert(data: dict) -> dict[str, float]:
    return {
        "dp":   _clamp(data.get("desire",   0.5)),
        "s":    _clamp(1.0 - data.get("sorrow",  0.0)),
        "ac":   _clamp(data.get("openness", 0.5)),
        "ox":   _clamp(1.0 - data.get("guilt",   0.0)),
        "gaba": _clamp(data.get("calm",     0.5)),
        "e":    _clamp(data.get("euphoria", 0.5)),
    }


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def print_mapping(raw: dict, nema: dict):
    """しーちゃん→Nema 変換を可視化"""
    print("  しーちゃん感情 → Nema NeuroState")
    print(f"  desire   {raw.get('desire',0):.3f} → dp   {nema['dp']:.3f}")
    print(f"  sorrow   {raw.get('sorrow',0):.3f} → s    {nema['s']:.3f}  (1-sorrow)")
    print(f"  openness {raw.get('openness',0):.3f} → ac   {nema['ac']:.3f}")
    print(f"  guilt    {raw.get('guilt',0):.3f} → ox   {nema['ox']:.3f}  (1-guilt)")
    print(f"  calm     {raw.get('calm',0):.3f} → gaba {nema['gaba']:.3f}")
    print(f"  euphoria {raw.get('euphoria',0):.3f} → e    {nema['e']:.3f}")


if __name__ == "__main__":
    nema_state, ts, raw = load_latest()
    print(f"しーちゃんの現在状態 ({ts})")
    print_mapping(raw, nema_state)
