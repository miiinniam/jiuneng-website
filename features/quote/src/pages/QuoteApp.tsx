/**
 * 报价页外壳：页头 + 模板条（内部）+ 步骤条 + 步骤表单 + 结果 + AI 助手。
 *
 * 口径（唯一口径，与 STEP_KEYS 一一对应）：
 *   /quote          公开 5 步：路线 → 货物分类 → 重量与明细 → 车型 → 提交确认
 *   /quote/internal 内部 6 步：路线 → 货物分类 → 重量与明细 → 车型 → 成本参数 → 提交确认
 * 公开版不渲染成本参数、模板、批量、DDP；地图与 AI 助手两边都有。
 * 公开版最后一页只做核对（ReviewStep），不做字段校验——校验已在前面各步拦过。
 * 数据只经 api.ts（CONTRACT §5），组件签名只按 CONTRACT §9 调用 D 的四件。
 */
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  QuoteApiError,
  fetchReference,
  geocode,
  hasInternalKey,
  isPublicQuoteResult,
  quoteRoute,
  setInternalKey,
} from '../api';
import type { PublicQuoteResult, ChatFormSnapshot, QuoteScope, ReferenceBundle } from '../api';
import type { LatLng, QuoteFormState, QuoteResponse, RouteGeometry } from '../engine/types';
import { useQuoteForm } from '../state/useQuoteForm';
import type { QuoteStep } from '../state/useQuoteForm';

import StepBar from '../components/wizard/StepBar';
import RouteStep from '../components/wizard/RouteStep';
import CargoClassStep from '../components/wizard/CargoClassStep';
import CargoStep from '../components/wizard/CargoStep';
import VehicleStep from '../components/wizard/VehicleStep';
import CostStep from '../components/wizard/CostStep';
import ReviewStep from '../components/wizard/ReviewStep';
import KeyGate from '../components/wizard/KeyGate';
import QuoteAside from '../components/wizard/QuoteAside';

import PublicResult from '../components/results/PublicResult';
import InternalResult from '../components/results/InternalResult';
import { isInternalResult } from '../components/results/ResultBits';

import TemplateBar from '../components/templates/TemplateBar';
// 批量面板带 xlsx（≈400KB），只有内部版用得到 —— 按需加载，别让客户版首包背它。
const BatchPanel = lazy(() => import('../components/batch/BatchPanel'));
import ChatPanel from '../components/ai/ChatPanel';
import { buildPlan } from '../components/workspace/plan';
import { planToText, type WsAction } from '../components/workspace/WorkspacePanel';
import { parseHints, parseRouteText } from '../components/workspace/parseHints';
import { useLang } from '../../../../src/shell/LangProvider';
import { shell } from '../i18n/shell';


/**
 * 每一步“缺什么”的提示顺序（与 useQuoteForm.problems 的键一致）。
 * 下标与步骤口径严格对齐：0 路线 · 1 货物分类 · 2 重量与明细 · 3 车型 · 4 成本（内部）/提交确认（公开）· 5 提交确认（仅内部）。
 * 公开版 4/5 不参与校验，见 reviewStep 的 stepOk 跳过逻辑。
 */
const STEP_KEYS: Record<number, (keyof QuoteFormState)[]> = {
  0: ['originLat', 'originLng', 'destLat', 'destLng'],
  1: ['cargoClass'],
  2: ['weightKg', 'cargoValueVnd'],
  3: ['vehicleModelId'],
  4: ['fuelPriceVnd', 'wageHourlyVnd', 'tollRateVndPerKm', 'miscCostVnd'],  // 内部版成本；公开版这一步是提交确认
  5: [],
};

const fixed = (n: number): string => (Number.isFinite(n) ? n.toFixed(6) : '');

/** 表单里类型为 string 的字段：AI 下发的补丁里这些是 number/boolean 原值 */
const STRING_FORM_KEYS = new Set([
  'originLat', 'originLng', 'destLat', 'destLng', 'weightKg', 'weightUnit',
  'cargoClass', 'cargoType', 'vehicleModelId',
]);

/**
 * 服务端 `form_patch` → `useQuoteForm.patch()` 的入参。
 * 只做一件必要的事：字符串字段收到 number/boolean 时转成字符串 —— 表单里 originLat / weightKg
 * 是 string，直接把数字塞进去会让 CargoStep 的 `form.weightKg.trim()` 抛 TypeError。
 * 补丁内容本身不动（键与取值由 server/tools/quoteTools.ts 决定）。
 */
function toFormPatch(p: Record<string, unknown>): Partial<QuoteFormState> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(p)) {
    if (STRING_FORM_KEYS.has(k) && (typeof v === 'number' || typeof v === 'boolean')) out[k] = String(v);
    else out[k] = v;
  }
  return out as Partial<QuoteFormState>;
}

/**
 * 表单 → 助手可见的快照（键与 `server/tools/quoteTools.ts` 的 QuoteFormSnapshot / 服务端
 * `sanitizeQuoteForm()` 白名单一一对应，camelCase）。
 * ⚠️ weightKg 折成**公斤**：服务端 runQuote 直接把 weightKg 当 weight_kg 送引擎，不做单位换算，
 *    所以配对的 weightUnit 恒为 'kg'（AI 的 set_cargo 也按 kg 回填，单位口径始终一致）。
 * 公开版表单没有 allowOversized 这个开关，因此不填。
 */
function buildChatForm(f: QuoteFormState): ChatFormSnapshot {
  const num = (v: string | null | undefined): number | undefined => {
    const s = v === null || v === undefined ? '' : String(v).trim();
    if (!s) return undefined;
    const n = Number(s);
    return Number.isFinite(n) ? n : undefined;
  };

  const items = f.items
    .filter((i) => i.lengthM > 0 && i.widthM > 0)
    .map((i) => ({
      id: i.id,
      name: i.name,
      lengthM: i.lengthM,
      widthM: i.widthM,
      ...(i.heightM === null ? {} : { heightM: i.heightM }),
      ...(i.weightKg === null ? {} : { weightKg: i.weightKg }),
      count: i.count,
      stackable: i.stackable,
      divisible: i.divisible === true,
    }));

  const rawWeight = num(f.weightKg);
  return {
    originLabel: f.originLabel || undefined,
    destLabel: f.destLabel || undefined,
    originLat: num(f.originLat),
    originLng: num(f.originLng),
    destLat: num(f.destLat),
    destLng: num(f.destLng),
    cargoClass: f.cargoClass || undefined,
    cargoType: f.cargoType || undefined,
    weightKg:
      rawWeight === undefined ? undefined : f.weightUnit === 'ton' ? rawWeight * 1000 : rawWeight,
    weightUnit: rawWeight === undefined ? undefined : 'kg',
    ...(items.length ? { items } : {}),
    vehicleModelId: f.vehicleModelId || undefined,
    needLoading: f.needLoading,
    needUnloading: f.needUnloading,
    needCrane: f.needCrane,
  };
}

export default function QuoteApp({ scope }: { scope: QuoteScope }) {
  const { lang } = useLang();
  const q = shell(lang);
  const internal = scope === 'internal';

  const [step, setStep] = useState<QuoteStep>(0);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle');
  const [result, setResult] = useState<PublicQuoteResult | QuoteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [keyGate, setKeyGate] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [reference, setReference] = useState<ReferenceBundle | null>(null);
  const [refFailed, setRefFailed] = useState(false);

  const { form, patch, apply, reset, toRequest, problems, canNext } = useQuoteForm({
    scope,
    status,
    result,
  });

  const resultsRef = useRef<HTMLDivElement | null>(null);
  const wizardRef = useRef<HTMLDivElement | null>(null);
  /** AI 解析出路线后是否要自动算一次（见 pickRoute / 自动测算 effect） */
  const autoQuote = useRef(false);

  /* ── 预热测算引擎 ─────────────────────────────────────────
     引擎在 Render 免费层，15 分钟无请求即休眠，唤醒约 40 秒。用户点「测算」时才去叫它，
     那 40 秒就白等了；这里在页面挂载时空跑一发 /api/health?deep=1（免鉴权，deep=1 会真实
     探测引擎），把冷启动藏进用户填表的时间窗口。
     失败静默：预热是体验优化，不该让页面因为引擎没醒而报错。 */
  useEffect(() => {
    fetch('/api/health?deep=1', { cache: 'no-store' }).catch(() => { /* 预热失败不影响页面 */ });
  }, []);

  /* ── 参考数据（车型库 / 货物类型 / 油价） ─────────────────── */
  useEffect(() => {
    let alive = true;
    fetchReference()
      .then((r) => {
        if (alive) setReference(r);
      })
      .catch(() => {
        if (alive) setRefFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  /* ── 提交测算 ──────────────────────────────────────────── */
  const runQuote = useCallback(async () => {
    setStatus('loading');
    setError(null);
    setResult(null);
    try {
      const r = await quoteRoute(toRequest(), scope);
      setResult(r);
      setStatus('ok');
    } catch (e) {
      if (e instanceof QuoteApiError) {
        // message 已是中文直出文案；reason 只用于分支，不展示给用户
        setError(e.message);
        if (internal && (e.status === 401 || e.reason === 'unauthorized')) setKeyGate(true);
      } else if ((e as Error)?.name === 'AbortError') {
        setStatus('idle');
        return;
      } else {
        setError(q.app.errSubmit);
      }
      setStatus('error');
    }
  }, [internal, scope, toRequest]);

  /* 出结果后把人带到面板（reduced-motion 下不滑） */
  useEffect(() => {
    if (status !== 'ok') return;
    const el = resultsRef.current;
    if (!el) return;
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }, [status]);

  /* ── 步骤口径与放行判定 ─────────────────────────────────
   * 公开 5 步 / 内部 6 步，标签数组本身就是唯一分母（total 由它推）。
   * 最后一页（提交确认）只核对：走完前面各步就算齐，不再校验表单。 */
  const labels = internal
    ? q.app.stepLabelsInternal
    : q.app.stepLabels;
  const total = scope === 'public' ? 5 : 6;
  const lastStep = (total - 1) as QuoteStep;
  /** 提交确认页：公开版 = 4，内部版 = 5 */
  const reviewStep = (internal ? 5 : 4) as QuoteStep;
  /* 提交按钮的可用性：前面每一步都放行即可（提交确认页不需要额外校验） */
  const allReady =
    canNext(0) && canNext(1) && canNext(2) && canNext(3) && (internal ? canNext(4) : true);
  /* 提交确认页恒为「已齐」：公开版跳过 4/5 的校验，免得拿成本字段去卡核对页 */
  const stepOk = step === reviewStep ? true : canNext(step);

  const firstProblem = (s: QuoteStep): string | null => {
    for (const k of STEP_KEYS[s] ?? []) {
      const msg = problems[k];
      if (msg) return msg;
    }
    return null;
  };
  const hint = stepOk ? null : firstProblem(step) ?? q.app.stepMissing;

  const goNext = () => setStep((s) => (s < lastStep ? ((s + 1) as QuoteStep) : s));
  const goPrev = () => setStep((s) => (s > 0 ? ((s - 1) as QuoteStep) : s));

  /** 跳到指定步并把人带回向导顶部（提交确认页的「修改」走这里；窄屏顺手收起助手面板） */
  const go = useCallback((n: number) => {
    setStep(n as QuoteStep);
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    wizardRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    if (typeof window !== 'undefined' && window.innerWidth < 768) setChatOpen(false);
  }, []);

  const backToRoute = () => go(0);

  const doReset = () => {
    reset();
    setStep(0);
    setResult(null);
    setError(null);
    setKeyGate(false);
    setStatus('idle');
  };

  /* ── 地图回传的几何线（能拿到就画在图上） ───────────────── */
  const geometry: RouteGeometry | null = isPublicQuoteResult(result)
    ? result.geometry ?? null
    : isInternalResult(result)
      ? result.route?.geometry ?? null
      : null;

  /* ── 语言：与官网同一套判定（?lang= → localStorage:jiuneng-lang → 浏览器 → zh） ── */

  /* ── 工作台：把「表单 + 引擎结果」投影成卡片（卡片上的数字只来自引擎） ── */
  const plan = useMemo(
    () => buildPlan({ form, result, reference, scope, lang }),
    [form, result, reference, scope, lang],
  );
  const cnyVnd = reference?.exchange_rate?.cny_vnd ?? null;
  const usdVnd = reference?.exchange_rate?.usd_vnd ?? null;

  /* ── 报价助手 ⇄ 表单：快照下行、补丁上行 ─────────────────
   * 快照只在 form 变化时重建：每帧换一个新对象会让 ChatPanel 的 send 反复重建。
   * 补丁直接走 useQuoteForm 的 patch()，因此 AI 改表单与用户手填走的是同一个状态机
   * （含「配车输入变了 ⇒ 旧推荐作废」那条规则）。 */
  const chatForm = useMemo(() => buildChatForm(form), [form]);
  const applyFormPatch = useCallback(
    (p: Record<string, unknown>) => {
      patch(toFormPatch(p));
    },
    [patch],
  );

  /* AI 测算结果 → 与「提交测算」（runQuote）成功后**同一条路径**：同一个 setter、同一个结果面板 */
  const applyQuoteResult = useCallback((r: Record<string, unknown>) => {
    if (!r || r.ok === false) return; // 服务端失败时不发这个事件，这里只防呆
    setResult(r as unknown as PublicQuoteResult);
    setStatus('ok');
  }, []);

  /** 工作台按钮 → 真实业务动作（不是「往输入框里塞一句话」） */
  const onWorkspaceAction = useCallback(
    (a: WsAction) => {
      if (a === 'copy') {
        if (plan) void navigator.clipboard?.writeText?.(planToText(plan, cnyVnd, lang));
        return;
      }
      if (a === 'recalc') {
        void runQuote();
        return;
      }
      if (a === 'contact') {
        window.location.assign('/contact');
        return;
      }
      const stepMap: Partial<Record<WsAction, QuoteStep>> = {
        'edit-route': 0,
        map: 0,
        // 卡片跳转按新口径：货物卡片改的是重量与明细（第 3 步），车型是第 4 步
        'edit-cargo': 2,
        'edit-vehicle': 3,
      };
      const target = stepMap[a];
      if (target === undefined) return;
      // 窄屏上助手面板是全屏的，go() 里会顺手收起，否则用户看不到被跳到的表单
      go(target);
    },
    [cnyVnd, go, plan, runQuote],
  );

  /* ── AI 助手的上下文与回填 ─────────────────────────────── */
  const aiContext: Record<string, unknown> = {
    scope,
    route: {
      origin: form.originLat && form.originLng ? { lat: Number(form.originLat), lng: Number(form.originLng) } : null,
      destination: form.destLat && form.destLng ? { lat: Number(form.destLat), lng: Number(form.destLng) } : null,
      waypoints: form.waypoints.filter((w) => Number.isFinite(w.lat) && Number.isFinite(w.lng)),
    },
    cargo: {
      weight_kg: form.weightUnit === 'ton' ? Number(form.weightKg || 0) * 1000 : Number(form.weightKg || 0),
      volume_m3: form.volumeM3 ? Number(form.volumeM3) : null,
      type: form.cargoType,
    },
    // 运输模式固定整车（拼货已下线，向导里不再给切换），这里不再透传 form.loadingMode，
    // 免得旧模板/存档把 consolidated 带进来，让 AI 按已废弃的口径回答。
    vehicle: { loading_mode: 'full_truck', vehicle_model_id: form.vehicleModelId || null },
    quote: isPublicQuoteResult(result)
      ? {
          distance_km: result.distance_km,
          duration_h: result.duration_h,
          vehicle_count: result.vehicle_count,
          price_low_vnd: result.price_low_vnd,
          price_high_vnd: result.price_high_vnd,
        }
      : isInternalResult(result)
        ? {
            distance_km: result.route?.distance_km ?? null,
            vehicle_count: result.breakdown?.vehicle_count ?? null,
            matched_vehicle_model_name: result.breakdown?.matched_vehicle_model_name ?? null,
          }
        : null,
  };

  const pickRoute = (origin: LatLng, destination: LatLng) => {
    patch({
      originLat: fixed(origin.lat),
      originLng: fixed(origin.lng),
      destLat: fixed(destination.lat),
      destLng: fixed(destination.lng),
    });
    // AI 把路线解析出来了 → 等表单凑齐就自动算一遍，卡片才能挂在回复下面。
    // 不立即算：patch 是异步的，且重量可能还没到。
    autoQuote.current = true;
  };

  /* 用户这句话里的重量/车型/货类/起终点 → 表单（数字仍由引擎算） */
  const handleHints = useCallback(
    (text: string) => {
      const h = parseHints(text, reference);
      const p: Partial<QuoteFormState> = {};
      if (h.weightKg) {
        p.weightKg = h.weightKg;
        p.weightUnit = 'ton';
      }
      if (h.vehicleModelId) p.vehicleModelId = h.vehicleModelId;
      if (h.cargoType) p.cargoType = h.cargoType;
      if (Object.keys(p).length) patch(p);

      // 「从友谊关到河内」→ 地理编码拿到坐标。AI 的回复里不一定带经纬度，
      // 但用户那句里一定有地名，这里补上，卡片才画得出来。
      const routeText = parseRouteText(text);
      if (!routeText) return;
      if (internal && !hasInternalKey()) return;
      void (async () => {
        try {
          const [a, b] = await Promise.all([geocode(routeText.from), geocode(routeText.to)]);
          const from = a[0];
          const to = b[0];
          if (!from || !to) return;
          patch({
            originLat: fixed(from.lat),
            originLng: fixed(from.lng),
            originLabel: routeText.from,
            destLat: fixed(to.lat),
            destLng: fixed(to.lng),
            destLabel: routeText.to,
          });
          autoQuote.current = true;
        } catch {
          /* 地理编码失败就算了：用户仍可在向导里手填坐标 */
        }
      })();
    },
    [internal, patch, reference],
  );

  /* 自动测算：路线 + 重量齐了就跑一次（内部版没口令时不打接口，免得弹 401） */
  useEffect(() => {
    if (!autoQuote.current || status === 'loading') return;
    const lat1 = Number(form.originLat);
    const lng1 = Number(form.originLng);
    const lat2 = Number(form.destLat);
    const lng2 = Number(form.destLng);
    const hasRoute = [lat1, lng1, lat2, lng2].every((n) => Number.isFinite(n) && n !== 0);
    const hasWeight = Number(form.weightKg) > 0;
    if (!hasRoute || !hasWeight) return;
    if (internal && !hasInternalKey()) return;
    autoQuote.current = false;
    void runQuote();
  }, [form.originLat, form.originLng, form.destLat, form.destLng, form.weightKg, internal, runQuote, status]);

  return (
    <div className="q-app">
      <header className="q-head">
        <div className="wrap">
          <div className="q-head-top">
            <p className="micro q-kicker">
              <span className="q-kicker-n">06</span>
              <span>{internal ? q.app.internalTag : q.app.publicTag}</span>
            </p>
            <div className="q-head-actions">
              {internal ? (
                <span className="micro q-key-state">{hasInternalKey() ? q.app.keyLoaded : q.app.keyNeeded}</span>
              ) : null}
              <button type="button" className="btn btn-outline q-ai-btn" onClick={() => setChatOpen(true)}>
                {q.app.aiBtn}
              </button>
            </div>
          </div>

          <h1 className="q-title">{internal ? q.app.titleInternal : q.app.titlePublic}</h1>
          <p className="q-lead">
            {internal
              ? q.app.ledeInternal
              : q.app.ledePublic}
          </p>
          <p className="q-head-note micro">
            {q.app.footNote}
          </p>
        </div>
      </header>

      <main className="q-main">
        <div className="wrap q-cols">
          {/* 左栏：向导主体（步骤条 + 当前步面板 + 结果）；右栏：设计稿的「当前填写」摘要卡 */}
          <div className="q-col-main">
          {internal ? (
            <div className="q-tpl-slot">
              <TemplateBar scope={scope} form={form} onApply={apply} />
            </div>
          ) : null}

          <div ref={wizardRef} className="q-wizard">
            <StepBar labels={labels} current={step} onJump={(s) => setStep(s)} />

            <div className="q-panel">
              {/* 0 路线 */}
              {step === 0 ? (
                <RouteStep form={form} patch={patch} problems={problems} geometry={geometry} />
              ) : null}
              {/* 1 货物分类（5 类，决定后续必填字段） */}
              {step === 1 ? (
                <CargoClassStep form={form} patch={patch} problems={problems} />
              ) : null}
              {/* 2 重量与明细 */}
              {step === 2 ? (
                <CargoStep form={form} patch={patch} problems={problems} reference={reference} />
              ) : null}
              {/* 3 车型（进入时静默自动配车） */}
              {step === 3 ? (
                <VehicleStep form={form} patch={patch} problems={problems} reference={reference} />
              ) : null}
              {/* 4 内部版 = 成本参数；公开版 = 提交确认（只核对，不填新值） */}
              {step === 4 ? (
                internal ? (
                  <CostStep form={form} patch={patch} problems={problems} />
                ) : (
                  <ReviewStep form={form} onEdit={go} />
                )
              ) : null}
              {/* 5 提交确认（仅内部版） */}
              {step === 5 && internal ? (
                <ReviewStep form={form} onEdit={go} />
              ) : null}
            </div>

            <div className="q-nav">
              {/* 设计稿的底部条：左边进度、右边操作。清空按钮保留（功能不能丢） */}
              <p className="q-foot-tip">第 {step + 1} 步 / 共 {labels.length} 步</p>
              <div className="q-nav-btns">
                {step > 0 ? (
                  <button type="button" className="btn btn-outline" onClick={goPrev}>
                    {q.app.prev}
                  </button>
                ) : null}

                {step < lastStep ? (
                  <button type="button" className="btn" disabled={!stepOk} onClick={goNext}>
                    {q.app.next}
                  </button>
                ) : (
                  /* 最后一步统一叫「提交测算」：公开版与内部版都走同一个 submit */
                  <button
                    type="button"
                    className="btn"
                    disabled={!allReady || status === 'loading'}
                    onClick={runQuote}
                  >
                    {status === 'loading' ? q.app.submitting : q.app.submitFinal}
                  </button>
                )}
              </div>

              <button type="button" className="q-reset" onClick={doReset}>
                {q.app.reset}
              </button>
            </div>

            {hint ? <p className="q-hint">{hint}</p> : null}

            {status === 'loading' ? (
              <p className="q-loading" role="status">
                {q.app.busyNote}
              </p>
            ) : null}

            {status === 'error' && error ? (
              <div className="q-error" role="alert">
                <span className="q-error-tag micro">{q.app.failTag}</span>
                <p className="q-error-msg">{error}</p>
                <button type="button" className="q-retry" onClick={runQuote}>
                  {q.app.retry}
                </button>
              </div>
            ) : null}

            {keyGate && internal ? (
              <KeyGate
                onConfirm={(key) => {
                  setInternalKey(key);
                  setKeyGate(false);
                  void runQuote();
                }}
                onCancel={() => {
                  setKeyGate(false);
                  setInternalKey(null);
                }}
              />
            ) : null}

            {refFailed ? (
              <p className="q-hint">{q.app.refFail}</p>
            ) : null}
          </div>

          {status === 'ok' && result ? (
            <section className="q-results" ref={resultsRef} aria-live="polite">
              <div className="q-results-head">
                <p className="micro">
                  {isPublicQuoteResult(result) ? q.app.resultPublic : q.app.resultInternal}
                </p>
                <button type="button" className="q-link" onClick={backToRoute}>
                  {q.app.editCond}
                </button>
              </div>

              {isPublicQuoteResult(result) ? (
                <PublicResult result={result} />
              ) : isInternalResult(result) ? (
                <InternalResult result={result} />
              ) : (
                <p className="q-note">{q.app.badResult}</p>
              )}

              {internal ? (
                <div className="q-batch-slot">
                  <Suspense fallback={<p className="q-note">{q.app.batchLoading}</p>}>
                    <BatchPanel scope={scope} />
                  </Suspense>
                </div>
              ) : null}
            </section>
          ) : null}
          </div>
          <QuoteAside form={form} />
        </div>
      </main>

      <ChatPanel
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        context={aiContext}
        onPickRoute={pickRoute}
        plan={plan}
        cnyVnd={cnyVnd}
        usdVnd={usdVnd}
        onWorkspaceAction={onWorkspaceAction}
        onHints={handleHints}
        lang={lang}
        form={chatForm}
        onFormPatch={applyFormPatch}
        onQuoteResult={applyQuoteResult}
      />

    </div>
  );
}
