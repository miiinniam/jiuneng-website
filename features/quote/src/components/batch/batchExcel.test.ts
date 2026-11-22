// 批量 Excel 的列名映射 / 校验 / 结果归一 —— 不需要浏览器的纯函数测试。
// 跑法：npx tsx --test features/quote/src/components/batch/batchExcel.test.ts

import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as XLSX from 'xlsx';
import {
  BATCH_COLUMNS,
  buildBatchTemplateWorkbook,
  buildHeaderLookup,
  parseBatchRecordSet,
  parseBatchWorkbook,
  toResultRows,
} from './batchExcel.ts';
import type { BatchRowResult } from '../../engine/types';

test('模板工作簿：两张表，表头就是 BATCH_COLUMNS 那一行', () => {
  const wb = buildBatchTemplateWorkbook();
  assert.deepEqual(wb.SheetNames, ['批量报价', '填写说明']);
  const sheet = wb.Sheets['批量报价'];
  const headers = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1 })[0];
  assert.deepEqual(headers, BATCH_COLUMNS.map((c) => c.header));
});

test('模板回读：两行示例能原样解析成 BatchRowInput（中文表头全命中）', () => {
  const parsed = parseBatchWorkbook(buildBatchTemplateWorkbook());
  assert.deepEqual(parsed.errors, []);
  assert.equal(parsed.rows.length, 2);
  const first = parsed.rows[0];
  assert.equal(first.origin_lat, 22.0051);
  assert.equal(first.origin_lng, 106.7498);
  assert.equal(first.dest_lat, 21.0285);
  assert.equal(first.weight_kg, 10000);
  assert.equal(first.loading_mode, 'full_truck');
  assert.equal(first.vehicle_model_id, 'high_side_10t');
  assert.equal(first.need_loading, true);
  assert.equal(first.empty_return, false);
  assert.equal(first.cargo_type, 'normal');
  assert.equal(first.cargo_value_vnd, 500000000);
  assert.equal(first.misc_cost_vnd, 0);
  // 第二行是拼货：体积必填、车型ID 留空
  assert.equal(parsed.rows[1].loading_mode, 'consolidated');
  assert.equal(parsed.rows[1].volume_m3, 28);
  assert.equal(parsed.rows[1].vehicle_model_id, undefined);
});

test('CSV（带空格/大小写差异的表头）也认', () => {
  const csv = [
    '起点纬度, 起点经度 ,终点纬度,终点经度,货物重量kg,货物体积m3,运输模式,车型ID,空车返回,需要装卸',
    '22.0051,106.7498,21.0285,105.8542,12000,35,full_truck,high_side_10t,否,是',
  ].join('\n');
  const wb = XLSX.read(csv, { type: 'string' });
  const parsed = parseBatchWorkbook(wb);
  assert.deepEqual(parsed.errors, []);
  assert.equal(parsed.rows.length, 1);
  assert.equal(parsed.rows[0].vehicle_model_id, 'high_side_10t');
  assert.equal(parsed.rows[0].volume_m3, 35);
  // 布尔列认「是/否」
  assert.equal(parsed.rows[0].empty_return, false);
  assert.equal(parsed.rows[0].need_loading, true);
});

test('英文字段名当别名同样能解析', () => {
  const rows = parseBatchRecordSet([
    {
      origin_lat: 22.0051,
      origin_lng: 106.7498,
      dest_lat: 21.0285,
      dest_lng: 105.8542,
      weight_kg: 9000,
      volume_m3: 20,
      loading_mode: 'consolidated',
      cargo_type: '',
    },
  ]);
  assert.deepEqual(rows.errors, []);
  assert.equal(rows.rows.length, 1);
  assert.equal(rows.rows[0].cargo_type, 'normal'); // 空即默认
  assert.equal(rows.rows[0].misc_cost_vnd, 0);
});

test('缺必填 / 模式非法 / 条件必填不满足：整行跳过并给出带行号的错误', () => {
  const bad = parseBatchRecordSet([
    // 第 2 行：缺重量
    { 起点纬度: 22.0051, 起点经度: 106.7498, 终点纬度: 21.0285, 终点经度: 105.8542, 运输模式: 'full_truck', 车型ID: 'x' },
    // 第 3 行：运输模式写法不对
    { 起点纬度: 22, 起点经度: 106, 终点纬度: 21, 终点经度: 105, 货物重量kg: 1000, 运输模式: '整车', 车型ID: 'x' },
    // 第 4 行：整车没填车型ID
    { 起点纬度: 22, 起点经度: 106, 终点纬度: 21, 终点经度: 105, 货物重量kg: 1000, 运输模式: 'full_truck' },
    // 第 5 行：拼货没填体积
    { 起点纬度: 22, 起点经度: 106, 终点纬度: 21, 终点经度: 105, 货物重量kg: 1000, 运输模式: 'consolidated' },
  ]);
  assert.equal(bad.rows.length, 0);
  assert.equal(bad.errors.length, 4);
  assert.match(bad.errors[0], /第 2 行缺少必填列：货物重量kg/);
  assert.match(bad.errors[1], /第 3 行「运输模式」必须是 consolidated 或 full_truck/);
  assert.match(bad.errors[2], /第 4 行：运输模式=full_truck（整车）必须填写车型ID/);
  assert.match(bad.errors[3], /第 5 行：运输模式=consolidated（拼货）必须填写货物体积m3/);
});

test('表头查找表：19 列，中文与字段名都能命中', () => {
  const lookup = buildHeaderLookup();
  assert.equal(BATCH_COLUMNS.length, 19);
  assert.equal(lookup.get('起点纬度'), 'origin_lat');
  assert.equal(lookup.get('origin_lat'), 'origin_lat');
  assert.equal(lookup.get('货物重量kg'), 'weight_kg');
  assert.equal(lookup.get('路桥费率vnd每km'), 'toll_rate_vnd_per_km'); // 归一后小写
});

test('toResultRows：成功行取里程/车数/成本，失败行只出错误文字', () => {
  const fake = [
    {
      row_index: 0,
      success: true,
      error: null,
      quote: {
        route: { distance_km: 172.35 },
        vehicle_count: 2,
        breakdown: { cost_total: 12345678, vehicle_count: 2 },
      },
    },
    { row_index: 1, success: false, error: '没有找到可用路线', quote: null },
  ] as unknown as BatchRowResult[];

  const rows = toResultRows(fake);
  assert.equal(rows[0].rowNumber, 1);
  assert.equal(rows[0].distanceKm, 172.35);
  assert.equal(rows[0].vehicleCount, 2);
  assert.equal(rows[0].costTotal, 12345678);
  assert.equal(rows[0].error, null);
  assert.equal(rows[1].rowNumber, 2);
  assert.equal(rows[1].distanceKm, null);
  assert.equal(rows[1].error, '没有找到可用路线');
});
