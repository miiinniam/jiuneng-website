// 来源：legacy/frontend/src/lib/batchExcel.ts（列名映射 + 逐行校验规则原样保留）。
// 为什么抽成独立文件：解析/建模板是纯函数，不需要 DOM，可以在 node 里跑测试
// （同目录 batchExcel.test.ts，命令 `npx tsx --test …`）。
// 只做「表格 ↔ BatchRowInput」的搬运，不碰报价逻辑（成本公式不在前端）。

import * as XLSX from 'xlsx';
import type { BatchRowInput, BatchRowResult, LoadingMode } from '../../engine/types';

/** 一列 = 一个 BatchRowInput 字段。表头文字即模板下载出来的表头，两处共用这一份。 */
export interface BatchColumn {
  header: string;
  key: keyof BatchRowInput;
  required: boolean;
}

export const BATCH_COLUMNS: BatchColumn[] = [
  { header: '起点纬度', key: 'origin_lat', required: true },
  { header: '起点经度', key: 'origin_lng', required: true },
  { header: '终点纬度', key: 'dest_lat', required: true },
  { header: '终点经度', key: 'dest_lng', required: true },
  { header: '货物重量kg', key: 'weight_kg', required: true },
  { header: '货物体积m3', key: 'volume_m3', required: false },
  { header: '货物类型', key: 'cargo_type', required: false },
  { header: '运输模式', key: 'loading_mode', required: true },
  { header: '车型ID', key: 'vehicle_model_id', required: false },
  { header: '空车返回', key: 'empty_return', required: false },
  { header: '需要装卸', key: 'need_loading', required: false },
  { header: '绕开禁限行', key: 'avoid_restricted_zones', required: false },
  { header: '绕开施工封闭', key: 'avoid_construction_zones', required: false },
  { header: '上坡山区附加费', key: 'via_mountain_road', required: false },
  { header: '货值VND', key: 'cargo_value_vnd', required: false },
  { header: '油价VND', key: 'fuel_price_vnd', required: false },
  { header: '工资VND', key: 'wage_hourly_vnd', required: false },
  { header: '路桥费率VND每km', key: 'toll_rate_vnd_per_km', required: false },
  { header: '其他费用VND', key: 'misc_cost_vnd', required: false },
];

const CARGO_TYPE_OPTIONS = 'normal / cold_chain / hazardous / oversized / other';
const LOADING_MODE_OPTIONS = 'consolidated（拼货，自动匹配车型）/ full_truck（整车，需指定车型ID）';

/** 表头归一：去空格/括号/大小写差异，客户从别处导出的表也能认。 */
function normHeader(raw: unknown): string {
  return String(raw ?? '')
    .replace(/[\s\u3000]/g, '')
    .replace(/[（）()]/g, '')
    .toLowerCase();
}

/** 归一表头 → 字段名。中文表头为主，字段名本身（英文）作别名兜底。 */
export function buildHeaderLookup(): Map<string, keyof BatchRowInput> {
  const map = new Map<string, keyof BatchRowInput>();
  for (const col of BATCH_COLUMNS) {
    map.set(normHeader(col.header), col.key);
    map.set(normHeader(col.key), col.key);
  }
  return map;
}

function readCell(record: Record<string, unknown>, lookup: Map<string, keyof BatchRowInput>, key: keyof BatchRowInput): unknown {
  // 先按原始表头直取（最常见路径），再按归一表头扫一遍（表头有空格/大小写差异）
  for (const col of BATCH_COLUMNS) {
    if (col.key === key && record[col.header] !== undefined) return record[col.header];
  }
  for (const [raw, value] of Object.entries(record)) {
    if (lookup.get(normHeader(raw)) === key) return value;
  }
  return undefined;
}

function cell(record: Record<string, unknown>, lookup: Map<string, keyof BatchRowInput>, key: keyof BatchRowInput): string {
  const v = readCell(record, lookup, key);
  if (v === undefined || v === null) return '';
  return String(v).trim();
}

function parseBool(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  const s = String(value ?? '').trim().toLowerCase();
  return s === 'true' || s === '1' || s === '是' || s === 'yes' || s === 'y' || s === 't';
}

function parseOptionalNumber(value: unknown): number | undefined {
  if (value === undefined || value === null || String(value).trim() === '') return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

function isBlank(value: unknown): boolean {
  return value === undefined || value === null || String(value).trim() === '';
}

export interface ParsedBatch {
  rows: BatchRowInput[];
  /** 逐行错误（已含 Excel 行号），这些行没有进 rows */
  errors: string[];
}

/** 解析器主体：与 legacy 一致——缺必填/模式非法/条件必填不满足的行整行跳过并记一条错误。 */
export function parseBatchRecordSet(raw: Record<string, unknown>[]): ParsedBatch {
  const lookup = buildHeaderLookup();
  const rows: BatchRowInput[] = [];
  const errors: string[] = [];

  raw.forEach((record, index) => {
    const rowNumber = index + 2; // 第 1 行是表头
    const missing = BATCH_COLUMNS.filter((c) => c.required && isBlank(readCell(record, lookup, c.key)));
    if (missing.length > 0) {
      errors.push(`第 ${rowNumber} 行缺少必填列：${missing.map((c) => c.header).join('、')}`);
      return;
    }

    const loadingMode = cell(record, lookup, 'loading_mode');
    if (loadingMode !== 'consolidated' && loadingMode !== 'full_truck') {
      errors.push(`第 ${rowNumber} 行「运输模式」必须是 consolidated 或 full_truck，实际是「${loadingMode}」`);
      return;
    }
    if (loadingMode === 'full_truck' && cell(record, lookup, 'vehicle_model_id') === '') {
      errors.push(`第 ${rowNumber} 行：运输模式=full_truck（整车）必须填写车型ID`);
      return;
    }
    if (loadingMode === 'consolidated' && cell(record, lookup, 'volume_m3') === '') {
      errors.push(`第 ${rowNumber} 行：运输模式=consolidated（拼货）必须填写货物体积m3`);
      return;
    }

    rows.push({
      origin_lat: Number(cell(record, lookup, 'origin_lat')),
      origin_lng: Number(cell(record, lookup, 'origin_lng')),
      dest_lat: Number(cell(record, lookup, 'dest_lat')),
      dest_lng: Number(cell(record, lookup, 'dest_lng')),
      weight_kg: Number(cell(record, lookup, 'weight_kg')),
      volume_m3: parseOptionalNumber(readCell(record, lookup, 'volume_m3')),
      cargo_type: cell(record, lookup, 'cargo_type') || 'normal',
      loading_mode: loadingMode as LoadingMode,
      vehicle_model_id: cell(record, lookup, 'vehicle_model_id') || undefined,
      empty_return: parseBool(readCell(record, lookup, 'empty_return')),
      need_loading: parseBool(readCell(record, lookup, 'need_loading')),
      avoid_restricted_zones: parseBool(readCell(record, lookup, 'avoid_restricted_zones')),
      avoid_construction_zones: parseBool(readCell(record, lookup, 'avoid_construction_zones')),
      via_mountain_road: parseBool(readCell(record, lookup, 'via_mountain_road')),
      cargo_value_vnd: parseOptionalNumber(readCell(record, lookup, 'cargo_value_vnd')),
      fuel_price_vnd: parseOptionalNumber(readCell(record, lookup, 'fuel_price_vnd')),
      wage_hourly_vnd: parseOptionalNumber(readCell(record, lookup, 'wage_hourly_vnd')),
      toll_rate_vnd_per_km: parseOptionalNumber(readCell(record, lookup, 'toll_rate_vnd_per_km')),
      misc_cost_vnd: parseOptionalNumber(readCell(record, lookup, 'misc_cost_vnd')) ?? 0,
    });
  });

  return { rows, errors };
}

/** 解析工作簿（取第一个 sheet） */
export function parseBatchWorkbook(workbook: XLSX.WorkBook): ParsedBatch {
  const sheetName = workbook.SheetNames[0];
  const sheet = workbook.Sheets[sheetName];
  if (!sheet) return { rows: [], errors: ['文件里没有可读的工作表'] };
  const raw = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
  if (raw.length === 0) return { rows: [], errors: ['表格是空的：第一行必须是表头，第二行起填数据'] };
  return parseBatchRecordSet(raw);
}

/** 浏览器侧：File.arrayBuffer() → 行。xlsx 0.20 认 xlsx/xls/csv。 */
export function parseBatchArrayBuffer(buffer: ArrayBuffer): ParsedBatch {
  let wb: XLSX.WorkBook;
  try {
    wb = XLSX.read(buffer, { type: 'array' });
  } catch {
    return { rows: [], errors: ['文件无法解析：请用模板另存为 .xlsx / .xls / .csv 后再上传'] };
  }
  return parseBatchWorkbook(wb);
}

/** 模板工作簿：表头 + 两行示例 + 填写说明 */
export function buildBatchTemplateWorkbook(): XLSX.WorkBook {
  const headers = BATCH_COLUMNS.map((c) => c.header);
  const rows: Record<string, string | number>[] = [
    {
      起点纬度: 22.0051,
      起点经度: 106.7498,
      终点纬度: 21.0285,
      终点经度: 105.8542,
      货物重量kg: 10000,
      货物体积m3: 40,
      货物类型: 'normal',
      运输模式: 'full_truck',
      车型ID: 'high_side_10t',
      空车返回: '否',
      需要装卸: '是',
      绕开禁限行: '否',
      绕开施工封闭: '否',
      上坡山区附加费: '否',
      货值VND: 500000000,
      油价VND: '',
      工资VND: '',
      路桥费率VND每km: '',
      其他费用VND: '',
    },
    {
      起点纬度: 20.8449,
      起点经度: 106.6881,
      终点纬度: 21.0285,
      终点经度: 105.8542,
      货物重量kg: 8000,
      货物体积m3: 28,
      货物类型: 'normal',
      运输模式: 'consolidated',
      车型ID: '',
      空车返回: '否',
      需要装卸: '否',
      绕开禁限行: '否',
      绕开施工封闭: '否',
      上坡山区附加费: '否',
      货值VND: '',
      油价VND: '',
      工资VND: '',
      路桥费率VND每km: '',
      其他费用VND: '',
    },
  ];

  const dataSheet = XLSX.utils.json_to_sheet(rows, { header: headers });
  dataSheet['!cols'] = headers.map((h) => ({ wch: Math.max(10, Math.min(18, h.length * 2 + 2)) }));

  const helpSheet = XLSX.utils.aoa_to_sheet([
    ['列名', '说明'],
    ['起点/终点纬度经度', '十进制度数，如 22.0051 / 106.7498；必填'],
    ['货物重量kg', '必填，单位公斤'],
    ['货物体积m3', '运输模式=consolidated（拼货）时必填，用来匹配车型运力；整车模式选填'],
    ['货物类型', `可选，不填默认 normal。可选值：${CARGO_TYPE_OPTIONS}`],
    ['运输模式', `必填。可选值：${LOADING_MODE_OPTIONS}`],
    ['车型ID', '运输模式=full_truck（整车）时必填，拼货模式忽略此列'],
    ['空车返回/需要装卸', '填 是/否 或 TRUE/FALSE，不填默认否'],
    ['绕开禁限行/绕开施工封闭/上坡山区附加费', '填 是/否 或 TRUE/FALSE，不填默认否；这两类路况需人工勾选'],
    ['货值VND/油价VND/工资VND/路桥费率VND每km/其他费用VND', '均可不填，不填则用系统默认值'],
  ]);
  helpSheet['!cols'] = [{ wch: 34 }, { wch: 78 }];

  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, dataSheet, '批量报价');
  XLSX.utils.book_append_sheet(workbook, helpSheet, '填写说明');
  return workbook;
}

/**
 * 浏览器侧：下载模板（表头 + 两行示例 + 填写说明）。
 * xlsx 的 writeFile 在浏览器里走 Blob 下载，在 node 里落盘，两边都能用。
 */
export function downloadBatchTemplate(filename = 'JIUNENG-批量报价模板.xlsx'): void {
  XLSX.writeFile(buildBatchTemplateWorkbook(), filename);
}

/** 单行结果里的展示字段（成本合计只有内部口径才存在） */
export interface BatchResultRow {
  rowNumber: number;
  distanceKm: number | null;
  vehicleCount: number | null;
  costTotal: number | null;
  error: string | null;
}

export function toResultRows(results: BatchRowResult[]): BatchResultRow[] {
  return results.map((r) => {
    const quote = r.quote;
    const costTotal =
      quote && quote.breakdown && typeof quote.breakdown.cost_total === 'number' ? quote.breakdown.cost_total : null;
    const vehicleCount =
      typeof quote?.vehicle_count === 'number'
        ? quote.vehicle_count
        : typeof quote?.breakdown?.vehicle_count === 'number'
          ? quote.breakdown.vehicle_count
          : null;
    return {
      rowNumber: r.row_index + 1,
      distanceKm: quote && typeof quote.route?.distance_km === 'number' ? quote.route.distance_km : null,
      vehicleCount,
      costTotal,
      error: !r.success ? r.error || '引擎没有返回这一行的结果' : null,
    };
  });
}
