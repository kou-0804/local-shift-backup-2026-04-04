import { useState } from 'react';
import * as api from '../api/mastersApi';
import type { RequestPreview } from '../types';

const currentMonth = (): string => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

/** HolidaySymbol legend (display only). */
const LEGEND: { symbol: string; meaning: string }[] = [
  { symbol: '☆', meaning: '公休希望' },
  { symbol: '★', meaning: '強制出勤' },
  { symbol: '夜', meaning: '夜勤希望' },
  { symbol: '17休', meaning: '17時退勤(休)' },
  { symbol: '17業', meaning: '17時退勤(業務)' },
];

/** 予定申請 — IMPORT ONLY (no CRUD). Upload CSV → preview (reports unresolved RSName) →
 *  commit per-month. The CSV is sent as raw bytes (the File itself), not multipart. */
export function RequestsImport({ setId }: { setId: number }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<RequestPreview | null>(null);
  const [ym, setYm] = useState<string>(currentMonth());
  const [importId, setImportId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onFile = async (f: File) => {
    setFile(f);
    setPreview(null);
    setImportId(null);
    setError(null);
    try {
      setPreview(await api.previewRequests(setId, f));
    } catch {
      setError('プレビューに失敗しました。CSVの内容を確認してください。');
    }
  };

  const onCommit = async () => {
    if (!file) return;
    const [year, month] = ym.split('-').map(Number);
    const res = await api.commitRequests(setId, year, month, file, 'web', file.name);
    setImportId(res.import_id);
  };

  return (
    <div className="requests-import">
      <h2>予定申請（取込）</h2>
      <p className="note">予定申請はインポート専用です（Power Apps が編集の正本）。</p>

      <details>
        <summary>記号の凡例</summary>
        <ul>
          {LEGEND.map((l) => (
            <li key={l.symbol}>
              {l.symbol}: {l.meaning}
            </li>
          ))}
        </ul>
      </details>

      <label>
        CSVファイル:{' '}
        <input
          type="file"
          accept=".csv,text/csv"
          data-testid="req-file"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void onFile(f);
          }}
        />
      </label>

      {error && <p role="alert">{error}</p>}

      {preview && (
        <div className="req-preview">
          <p>取込予定 {preview.row_count} 行</p>
          {preview.unresolved.length > 0 && (
            <div role="alert" className="unresolved">
              <strong>未解決のRSName（取込前に確認）:</strong>
              <ul>
                {preview.unresolved.map((u) => (
                  <li key={u}>{u}</li>
                ))}
              </ul>
            </div>
          )}
          <table>
            <thead>
              <tr>
                <th>日付</th>
                <th>記号</th>
                <th>RSName</th>
                <th>技師ID</th>
                <th>状態</th>
              </tr>
            </thead>
            <tbody>
              {preview.rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.date}</td>
                  <td>{r.symbol}</td>
                  <td>{r.raw_rsname}</td>
                  <td>{r.tech_id_resolved ?? '-'}</td>
                  <td>{r.resolve_status}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <label>
            取込先（年月）:{' '}
            <input type="month" data-testid="req-month" value={ym} onChange={(e) => setYm(e.target.value)} />
          </label>
          <button type="button" data-testid="req-commit" onClick={() => void onCommit()}>
            この年月に取込
          </button>
        </div>
      )}

      {importId != null && <p role="status">取込が完了しました（import_id={importId}）。</p>}
    </div>
  );
}
