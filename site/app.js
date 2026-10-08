'use strict';
const el = id => document.getElementById(id);
const currency = value => value === null ? '不限' : '¥' + Number(value).toLocaleString('zh-CN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const datetime = value => new Date(value).toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai', hour12: false});
let loading = false;
function cell(row, text, className) {
  const td = document.createElement('td');
  td.textContent = text;
  td.className = className;
  row.append(td);
  return td;
}
function render(data) {
  const fragment = document.createDocumentFragment();
  for (const record of data.rows) {
    const row = document.createElement('tr');
    cell(row, record.name || '未命名', 'name');
    const low = !record.unlimited && Number(record.total) > 0 && Number(record.remaining) / Number(record.total) <= 0.1;
    cell(row, currency(record.remaining), 'number balance' + (low ? ' low' : ''));
    cell(row, currency(record.total), 'number amount secondary-col');
    cell(row, currency(record.used), 'number amount');
    const statusCell = cell(row, '', 'status-col');
    const badge = document.createElement('span');
    badge.textContent = record.status;
    badge.className = 'status' + (record.status === '启用' ? ' active' : '');
    statusCell.append(badge);
    fragment.append(row);
  }
  el('rows').replaceChildren(fragment);
  el('count').textContent = data.updated_at ? `${data.rows.length} 位成员` : '等待同步';
  el('table-wrap').hidden = data.rows.length === 0;
  el('empty').hidden = data.rows.length !== 0;
  el('empty-title').textContent = data.updated_at ? '暂无成员记录' : '等待首次同步';
  el('empty-text').textContent = data.updated_at ? '当前没有可展示的额度记录。' : '管理员完成连接后，所有成员的余额会在这里显示。';
  el('updated').textContent = data.updated_at ? '数据更新于 ' + datetime(data.updated_at) + '（北京时间）' : '尚未同步';
  const interval = Number(data.sync_interval_seconds);
  el('interval').textContent = `计划每 ${Math.round(interval / 60)} 分钟同步一次`;
  const updated = Date.parse(data.updated_at);
  const stale = !Number.isFinite(updated) || !Number.isFinite(interval) || interval < 60 || Date.now() - updated > interval * 2000 + 60000;
  el('notice').hidden = !stale;
  el('notice').className = 'notice' + (data.updated_at && stale ? ' warning' : '');
  el('notice').textContent = data.updated_at ? '数据更新延迟。以下为上次成功同步的记录。' : '等待首次同步。';
}
async function refresh() {
  if (loading) return;
  loading = true;
  el('refresh').disabled = true;
  el('refresh').textContent = '刷新中…';
  try {
    const response = await fetch('./usage.json', {cache: 'no-store', signal: AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error('Unavailable');
    render(await response.json());
  } catch (_) {
    el('notice').hidden = false;
    el('notice').className = 'notice warning';
    el('notice').textContent = '页面暂时无法连接服务。已有数据可能不是最新，请稍后刷新。';
    if (!el('rows').children.length) el('empty').hidden = false;
  } finally {
    loading = false;
    el('refresh').disabled = false;
    el('refresh').textContent = '刷新页面';
  }
}
el('refresh').addEventListener('click', refresh);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
setInterval(() => { if (!document.hidden) refresh(); }, 60000);
refresh();
