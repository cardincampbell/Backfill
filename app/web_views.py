import html as html_lib

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
import aiosqlite

from app.db.database import get_db
from app.db import queries

router = APIRouter(tags=["web"])

e = html_lib.escape  # short alias


@router.get("/", response_class=HTMLResponse)
async def home(db: aiosqlite.Connection = Depends(get_db)):
    summary = await queries.get_dashboard_summary(db)
    locations = await queries.list_locations(db)
    shifts = await queries.list_shifts(db)
    audits = await queries.list_audit_log(db, limit=10)

    location_rows = "".join(
        f"<tr><td>{r['id']}</td><td>{e(r['name'])}</td><td>{e(r.get('manager_name') or '')}</td><td>{e(r.get('scheduling_platform') or '')}</td></tr>"
        for r in locations[:10]
    )
    shift_rows = "".join(
        f"<tr><td>{s['id']}</td><td>{e(s['role'])}</td><td>{e(str(s['date']))}</td><td>{e(s['status'])}</td><td>{e(s.get('fill_tier') or '')}</td></tr>"
        for s in shifts[:10]
    )
    audit_rows = "".join(
        f"<tr><td>{e(str(a['timestamp']))}</td><td>{e(a['action'])}</td><td>{e(a.get('entity_type') or '')}</td><td>{a.get('entity_id') or ''}</td></tr>"
        for a in audits
    )

    html = f"""
    <html>
      <head>
        <title>Backfill Native Lite</title>
        <style>
          body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; color: #111; background: #f7f6f2; }}
          h1, h2 {{ margin-bottom: 8px; }}
          .grid {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 16px; margin: 24px 0; }}
          .card {{ background: white; border-radius: 12px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
          table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 12px; overflow: hidden; }}
          th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #ece7df; }}
          .section {{ margin-top: 28px; }}
          code {{ background: #efe8dd; padding: 2px 6px; border-radius: 6px; }}
        </style>
      </head>
      <body>
        <h1>Backfill Native Lite</h1>
        <p>Support-layer dashboard for roster, shifts, cascade status, and recent audit activity.</p>
        <div class="grid">
          <div class="card"><strong>Locations</strong><div>{summary['locations']}</div></div>
          <div class="card"><strong>Workers</strong><div>{summary['workers']}</div></div>
          <div class="card"><strong>Vacant Shifts</strong><div>{summary['shifts_vacant']}</div></div>
          <div class="card"><strong>Active Cascades</strong><div>{summary['cascades_active']}</div></div>
        </div>
        <div class="section">
          <h2>Locations</h2>
          <table><thead><tr><th>ID</th><th>Name</th><th>Manager</th><th>Platform</th></tr></thead><tbody>{location_rows}</tbody></table>
        </div>
        <div class="section">
          <h2>Recent Shifts</h2>
          <table><thead><tr><th>ID</th><th>Role</th><th>Date</th><th>Status</th><th>Fill Tier</th></tr></thead><tbody>{shift_rows}</tbody></table>
        </div>
        <div class="section">
          <h2>Recent Audit Log</h2>
          <table><thead><tr><th>Timestamp</th><th>Action</th><th>Entity Type</th><th>Entity ID</th></tr></thead><tbody>{audit_rows}</tbody></table>
        </div>
        <div class="section">
          <p>API surfaces remain available under <code>/api</code>.</p>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(content=html)
