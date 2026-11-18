/**
 * 车辆匹配与超限核查。
 *
 * 契约：`POST /api/fleet-match` → `{ok, groups[], total_trucks, oversize{blocked,basis}}`。
 * 只显示白名单字段；响应里的 `breakdown` / 金额 / `locked` 一律不渲染（服务端已丢弃，前端也不读）。
 * 超限判定以「单件最大尺寸」为准：长宽留空时服务端按 0 处理（只按重量配车），页面必须把这件事说清楚。
 */
import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { errorText, fmtDecimal, fmtInt, postFleetMatch, reasonText, type FleetItem, type FleetResult } from './api';
import { Disclaim, ErrorLine } from './parts';

type Row = {
  key: number;
  name: string;
  length: string;
  width: string;
  height: string;
  weight: string;
  count: string;
  stackable: boolean;
};

let seq = 0;
const newRow = (): Row => ({
  key: (seq += 1),
  name: '',
  length: '',
  width: '',
  height: '',
  weight: '',
  count: '1',
  stackable: false,
});

/** 已知 6 个官网车型的中文名；未知型号回落到服务端给的 `category`，不硬猜。 */
const MODEL_LABEL: Record<string, string> = {
  flatbed_13m: '普通平板 13 米',
  flatbed_low_17m5: '低平板 17.5 米',
  flatbed_low_13m: '低平板 13 米',
  flatbed_12m5: '普通平板 12.5 米',
  small_box_10t: '10 吨厢式货车',
  small_box_5t: '5 吨厢式货车',
};

function num(raw: string): number {
  const value = Number(raw);
  return raw.trim() && Number.isFinite(value) ? value : 0;
}

export default function FleetForm() {
  const [rows, setRows] = useState<Row[]>([newRow()]);
  const [weight, setWeight] = useState('');
  const [volume, setVolume] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<FleetResult | null>(null);

  const rowWeight = useMemo(
    () => rows.reduce((sum, row) => sum + num(row.weight) * Math.max(1, num(row.count) || 1), 0),
    [rows],
  );

  const patch = (key: number, next: Partial<Row>) => {
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...next } : row)));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;

    const items: FleetItem[] = [];
    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i];
      const kg = num(row.weight);
      if (kg <= 0) {
        setError(`第 ${i + 1} 件：单件重量需为大于 0 的数值（kg）。`);
        return;
      }
      const count = Math.max(1, Math.round(num(row.count) || 1));
      if (count > 50) {
        setError(`第 ${i + 1} 件：件数需为 1–50 的整数。`);
        return;
      }
      const height = num(row.height);
      items.push({
        ...(row.name.trim() ? { name: row.name.trim() } : {}),
        length_m: Math.max(0, num(row.length)),
        width_m: Math.max(0, num(row.width)),
        ...(height > 0 ? { height_m: height } : {}),
        weight_kg: kg,
        count,
        stackable: row.stackable,
      });
    }

    const totalWeight = num(weight) > 0 ? num(weight) : rowWeight;
    if (totalWeight <= 0) {
      setError('请填写货物总重（kg），或在明细里填写单件重量。');
      return;
    }

    setError('');
    setBusy(true);
    try {
      const data = await postFleetMatch({
        weight_kg: totalWeight,
        volume_m3: num(volume) > 0 ? num(volume) : null,
        cargo_type: 'normal',
        items,
      });
      setResult(data);
    } catch (err) {
      setError(errorText(err));
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  const okResult = result && result.ok ? result : null;
  const failResult = result && !result.ok ? result : null;
  const groups = okResult?.groups ?? [];

  return (
    <div className="t-grid">
      <form className="t-form" onSubmit={submit} noValidate>
        <div className="t-form-head">
          <p className="micro">输入</p>
          <h2 className="t-h2">货物明细</h2>
        </div>

        <div className="t-fields t-fields-2">
          <label className="t-field">
            <span className="t-label">
              货物总重（kg）<span className="t-opt">留空按明细汇总</span>
            </span>
            <input
              className="t-input"
              type="number"
              inputMode="numeric"
              min={0}
              step={100}
              placeholder={rowWeight > 0 ? String(Math.round(rowWeight)) : '例如 18000'}
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
            />
          </label>

          <label className="t-field">
            <span className="t-label">
              总体积（m³）<span className="t-opt">选填</span>
            </span>
            <input
              className="t-input"
              type="number"
              inputMode="decimal"
              min={0}
              step={0.1}
              value={volume}
              onChange={(e) => setVolume(e.target.value)}
            />
          </label>
        </div>

        <div className="t-rows">
          <div className="t-rows-head">
            <p className="t-label">逐件明细</p>
            <p className="t-hint">超限按单件最大尺寸判定；长宽留空时只按重量配车，不出超限结论。</p>
          </div>

          {rows.map((row, index) => (
            <fieldset className="t-row" key={row.key} data-testid="fleet-row">
              <legend className="t-row-legend">第 {index + 1} 件</legend>
              <div className="t-row-grid">
                <label className="t-field t-span-2">
                  <span className="t-label">名称</span>
                  <input
                    className="t-input"
                    type="text"
                    placeholder="如 风机叶片 / 变压器"
                    value={row.name}
                    onChange={(e) => patch(row.key, { name: e.target.value })}
                  />
                </label>
                <label className="t-field">
                  <span className="t-label">长（m）</span>
                  <input
                    className="t-input"
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step={0.1}
                    value={row.length}
                    onChange={(e) => patch(row.key, { length: e.target.value })}
                  />
                </label>
                <label className="t-field">
                  <span className="t-label">宽（m）</span>
                  <input
                    className="t-input"
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step={0.1}
                    value={row.width}
                    onChange={(e) => patch(row.key, { width: e.target.value })}
                  />
                </label>
                <label className="t-field">
                  <span className="t-label">
                    高（m）<span className="t-opt">选填</span>
                  </span>
                  <input
                    className="t-input"
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step={0.1}
                    value={row.height}
                    onChange={(e) => patch(row.key, { height: e.target.value })}
                  />
                </label>
                <label className="t-field">
                  <span className="t-label">单件重量（kg）</span>
                  <input
                    className="t-input"
                    type="number"
                    inputMode="numeric"
                    min={0}
                    step={100}
                    value={row.weight}
                    onChange={(e) => patch(row.key, { weight: e.target.value })}
                  />
                </label>
                <label className="t-field">
                  <span className="t-label">件数</span>
                  <input
                    className="t-input"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    step={1}
                    value={row.count}
                    onChange={(e) => patch(row.key, { count: e.target.value })}
                  />
                </label>
                <label className="t-check">
                  <input
                    type="checkbox"
                    checked={row.stackable}
                    onChange={(e) => patch(row.key, { stackable: e.target.checked })}
                  />
                  <span>可叠放</span>
                </label>
              </div>
              {rows.length > 1 ? (
                <button
                  type="button"
                  className="t-btn-text"
                  onClick={() => setRows((prev) => prev.filter((item) => item.key !== row.key))}
                >
                  删除本行
                </button>
              ) : null}
            </fieldset>
          ))}

          <button
            type="button"
            className="t-btn-ghost t-add"
            data-testid="fleet-add"
            onClick={() => setRows((prev) => [...prev, newRow()])}
          >
            添加一行
          </button>
        </div>

        <ErrorLine text={error} testId="fleet-error" />

        <div className="t-actions">
          <button type="submit" className="t-btn" data-testid="fleet-submit" disabled={busy}>
            {busy ? '匹配中…' : '匹配车型'}
          </button>
          <span className="t-busy">按尺寸与重量给出建议，不代表已确认车辆可用</span>
        </div>
      </form>

      <section className="t-out" data-testid="fleet-result" aria-live="polite">
        <div className="t-out-head">
          <p className="micro">结果</p>
          <h2 className="t-h2">建议车型 · 需车数 · 超限</h2>
        </div>

        {busy ? <p className="t-hint">正在匹配车型…</p> : null}

        {!busy && !result ? <p className="t-hint">填写货物明细后点「匹配车型」，结果会显示在这里。</p> : null}

        {!busy && failResult ? (
          <p className="t-err" role="alert">
            {failResult.note || reasonText(failResult.reason)}
          </p>
        ) : null}

        {!busy && okResult ? (
          <>
            <dl className="t-stats">
              <div className="t-stat">
                <dt>合计车数</dt>
                <dd>
                  <span className="t-num">{fmtInt(okResult.total_trucks)}</span> 台
                </dd>
              </div>
            </dl>

            <div className="t-groups">
              {groups.length === 0 ? <p className="t-hint">未得到可用车型组合，请联系项目经理。</p> : null}
              {groups.map((group) => (
                <article className="t-group" key={`${group.model}-${group.category}`}>
                  <header className="t-group-head">
                    <p className="t-group-name">{MODEL_LABEL[group.model] ?? group.category}</p>
                    <p className="t-num">
                      {fmtDecimal(group.vehicle_count, 0)} 台
                    </p>
                  </header>
                  <p className="t-group-meta">
                    {group.category}
                    {group.reason ? ` · ${group.reason}` : ''}
                  </p>
                  {Array.isArray(group.flags) && group.flags.length > 0 ? (
                    <ul className="t-flags">
                      {group.flags.map((flag) => (
                        <li key={flag}>{flag}</li>
                      ))}
                    </ul>
                  ) : null}
                </article>
              ))}
            </div>

            <div
              className={okResult.oversize?.blocked ? 't-warn t-warn-strong' : 't-ok-line'}
              data-testid="fleet-oversize"
            >
              <p className="t-label">超限判定</p>
              <p>
                {okResult.oversize?.blocked
                  ? '判定为超限货物：需走专项运输方案与超限许可，本条不在线上直接给方案。'
                  : '未触发超限阈值，可按常规车辆组织运输。'}
              </p>
              {okResult.oversize?.basis ? <p className="t-hint">{okResult.oversize.basis}</p> : null}
            </div>

            <p className="t-out-foot">
              车型为初步匹配结果，实际车辆可用性以项目经理确认为准；超限线路需另办许可。
            </p>
          </>
        ) : null}

        <Disclaim />
      </section>
    </div>
  );
}
