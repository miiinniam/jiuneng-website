/**
 * 批量 Excel 面板（仅内部版）。
 * 签名见 features/quote/CONTRACT.md §9，C 代理按此签名调用，**不得改动签名**。
 *
 * 口径：公开版直接 return null（批量是内部能力，客户版连入口都不该有）。
 * 链路：选文件 → batchExcel 解析成 BatchRowInput[] → batchQuote(rows) → 结果表。
 * 列名映射、模板生成、结果归一都在 ./batchExcel.ts（纯函数，可脱浏览器测）。
 */

import { useCallback, useRef, useState } from 'react';
import type { QuoteScope } from '../../api';
import { batchQuote, QuoteApiError } from '../../api';
import type { BatchRowInput } from '../../engine/types';
import { formatVnd } from '../../engine/format';
import { panelsText } from '../../i18n/panels';
import { useLang } from '../../../../../src/shell/LangProvider';

import {
  downloadBatchTemplate,
  parseBatchArrayBuffer,
  toResultRows,
  type BatchResultRow,
} from './batchExcel';

export type BatchPanelProps = { scope: QuoteScope };

type Phase = 'idle' | 'parsing' | 'quoting' | 'done';

export default function BatchPanel({ scope }: BatchPanelProps) {
  const { lang } = useLang();
  const bp = panelsText(lang);
  const [phase, setPhase] = useState<Phase>('idle');
  const [fileName, setFileName] = useState('');
  const [rows, setRows] = useState<BatchRowInput[]>([]);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [results, setResults] = useState<BatchResultRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const busy = phase === 'parsing' || phase === 'quoting';

  const onChange = useCallback(async (file: File | undefined) => {
    if (!file) return;
    setFileName(file.name);
    setPhase('parsing');
    setError(null);
    setResults([]);
    setParseErrors([]);
    setRows([]);

    try {
      const buffer = await file.arrayBuffer();
      const parsed = parseBatchArrayBuffer(buffer);
      setParseErrors(parsed.errors);
      setRows(parsed.rows);

      if (parsed.rows.length === 0) {
        setPhase('idle');
        return;
      }

      setPhase('quoting');
      const out = await batchQuote(parsed.rows);
      setResults(toResultRows(out));
      setPhase('done');
    } catch (e) {
      setPhase('idle');
      setError(e instanceof QuoteApiError ? e.message : bp.batch.fail);
    }
  }, []);

  const reset = () => {
    setPhase('idle');
    setFileName('');
    setRows([]);
    setParseErrors([]);
    setResults([]);
    setError(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  if (scope !== 'internal') return null;

  const okCount = results.filter((r) => !r.error).length;
  const failCount = results.length - okCount;

  return (
    <section className="q-batch" aria-label={bp.batch.aria}>
      <div className="q-batch-head">
        <div>
          <p className="micro">Batch</p>
          <h3 className="q-batch-title">{bp.batch.title}</h3>
        </div>
        <div className="q-batch-actions">
          <button type="button" className="q-batch-btn q-batch-btn--quiet" onClick={() => downloadBatchTemplate()}>
            {bp.batch.download}
          </button>
          <label className={`q-batch-file${busy ? ' q-batch-file--busy' : ''}`}>
            <span>{busy ? bp.batch.processing : bp.batch.choose}</span>
            <input
              ref={inputRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              disabled={busy}
              onChange={(e) => void onChange(e.target.files?.[0])}
            />
          </label>
          {(rows.length > 0 || results.length > 0 || error) && (
            <button type="button" className="q-batch-btn q-batch-btn--quiet" onClick={reset} disabled={busy}>
              {bp.batch.clear}
            </button>
          )}
        </div>
      </div>

      <p className="q-batch-note">
        {bp.batch.hint}
      </p>

      {fileName && (
        <p className="q-batch-file-name micro">
          {fileName}
          {rows.length > 0 && bp.batch.parsed(rows.length)}
          {phase === 'quoting' && bp.batch.quoting}
          {phase === 'done' && bp.batch.done(okCount, failCount)}
        </p>
      )}

      {error && <p className="q-batch-err">{error}</p>}

      {parseErrors.length > 0 && (
        <div className="q-batch-errors">
          <p className="micro">{bp.batch.notSubmitted(parseErrors.length)}</p>
          <ul>
            {parseErrors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {results.length > 0 && (
        <div className="q-batch-table-wrap">
          <table className="q-batch-table">
            <thead>
              <tr>
                <th scope="col">{bp.batch.thRow}</th>
                <th scope="col">{bp.batch.thKm}</th>
                <th scope="col">{bp.batch.thTrucks}</th>
                <th scope="col">{bp.batch.thCost}</th>
                <th scope="col">{bp.batch.thError}</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.rowNumber} className={r.error ? 'q-batch-row--fail' : undefined}>
                  <td>{r.rowNumber}</td>
                  <td>{r.distanceKm === null ? '—' : r.distanceKm.toFixed(1)}</td>
                  <td>{r.vehicleCount === null ? '—' : r.vehicleCount}</td>
                  <td>{r.costTotal === null ? '—' : formatVnd(r.costTotal)}</td>
                  <td>{r.error ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {phase === 'idle' && !fileName && (
        <p className="q-batch-note q-batch-note--quiet">
          {bp.batch.note}
        </p>
      )}
    </section>
  );
}
