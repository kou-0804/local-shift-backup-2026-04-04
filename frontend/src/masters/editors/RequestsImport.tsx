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

/** 予定申請 — IMPORT ONLY (no CRUD). Two ways to feed the same preview→commit flow:
 *  (1) paste the Power Apps clipboard (TAB-separated) directly, or (2) upload a CSV
 *  file. The body is sent as raw bytes/text; the backend sniffs TAB vs comma and
 *  normalizes a paste to canonical comma CSV. */
export function RequestsImport({ setId }: { setId: number }) {
  // The previewed source — either the uploaded File or the pasted text — so commit
  // sends exactly what was previewed.
  const [source, setSource] = useState<{ body: File | string; name: string } | null>(null);
  const [pasteText, setPasteText] = useState('');
  const [preview, setPreview] = useState<RequestPreview | null>(null);
  const [ym, setYm] = useState<string>(currentMonth());
  const [importId, setImportId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runPreview = async (body: File | string, name: string) => {
    setSource({ body, name });
    setPreview(null);
    setImportId(null);
    setError(null);
    try {
      setPreview(await api.previewRequests(setId, body));
    } catch {
      setError('プレビューに失敗しました。内容（区切り・列名）を確認してください。');
    }
  };

  const onPaste = () => {
    if (!pasteText.trim()) {
      setError('貼り付け内容が空です。Power Apps の「CSV出力」後に貼り付けてください。');
      return;
    }
    void runPreview(pasteText, '貼り付け.csv');
  };

  const onCommit = async () => {
    if (!source) return;
    const [year, month] = ym.split('-').map(Number);
    const res = await api.commitRequests(setId, year, month, source.body, 'web', source.name);
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

      <section className="import-source">
        <h3>① クリップボードから貼り付け（推奨）</h3>
        <p className="note">
          Power Apps の「CSV出力」ボタンを押すとコピーされます。下の欄に貼り付け（タブ区切りのままでOK）→「貼り付けを確認」。
        </p>
        <textarea
          data-testid="req-paste"
          value={pasteText}
          onChange={(e) => setPasteText(e.target.value)}
          rows={6}
          placeholder={'HolidaySymbol\tPPPDate\tRSName\n◆\t2026/07/01\t03 矢野　昌男 …'}
          style={{ width: '100%', fontFamily: 'monospace', fontSize: 12 }}
        />
        <button type="button" data-testid="req-paste-preview" onClick={onPaste}>
          貼り付けを確認
        </button>
      </section>

      <section className="import-source">
        <h3>② CSVファイルから取込</h3>
        <label>
          CSVファイル:{' '}
          <input
            type="file"
            accept=".csv,text/csv"
            data-testid="req-file"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void runPreview(f, f.name);
            }}
          />
        </label>
      </section>

      {error && <p role="alert">{error}</p>}

      {preview && (
        <div className="req-preview">
          <p>
            取込予定 {preview.row_count} 行
            {typeof preview.skipped === 'number' && preview.skipped > 0 && (
              <>（スキップ {preview.skipped} 行: Sample/空欄）</>
            )}
          </p>
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
