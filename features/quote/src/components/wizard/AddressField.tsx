/**
 * 地址搜索：输入 300ms 防抖 → geocode() → 下拉候选 → 选中回调（含 lat/lng）。
 * 服务端失败也返回空数组，所以“搜不到”只提示、不报错（CONTRACT §3.1）。
 */
import { useEffect, useRef, useState } from 'react';
import { geocode } from '../../api';
import type { GeoResult } from '../../api';
import { mapText } from '../../i18n/map';
import { useLang } from '../../../../../src/shell/LangProvider';


export default function AddressField({
  placeholder,
  onSelect,
  ariaLabel,
}: {
  placeholder: string;
  onSelect: (r: GeoResult) => void;
  ariaLabel: string;
}) {
  const { lang } = useLang();
  const m = mapText(lang);
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<GeoResult[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const skip = useRef(false);
  const seq = useRef(0);

  useEffect(() => {
    if (skip.current) {
      skip.current = false;
      return;
    }
    const term = query.trim();
    if (term.length < 2) {
      setItems([]);
      setOpen(false);
      setBusy(false);
      setSearched(false);
      return;
    }

    const timer = setTimeout(() => {
      const mine = ++seq.current;
      setBusy(true);
      geocode(term)
        .then((found) => {
          if (mine !== seq.current) return;
          setItems(found);
          setSearched(true);
          setOpen(found.length > 0);
        })
        .catch(() => {
          if (mine !== seq.current) return;
          setItems([]);
          setSearched(true);
          setOpen(false);
        })
        .finally(() => {
          if (mine === seq.current) setBusy(false);
        });
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  const pick = (r: GeoResult) => {
    skip.current = true; // 回填后不要再触发一次搜索
    setQuery(r.label);
    setItems([]);
    setOpen(false);
    // 选中后必须把 searched 归位：否则 `!open && searched && items.length===0`
    // 会继续渲染「没有匹配地址」——用户明明已经选好了（实测被验收脚本抓到）
    setSearched(false);
    onSelect(r);
  };

  return (
    <div className="q-addr">
      <div className="q-addr-row">
        <input
          className="q-input q-addr-input"
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-label={ariaLabel}
          aria-autocomplete="list"
          autoComplete="off"
          placeholder={placeholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => items.length > 0 && setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 160)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setOpen(false);
            if (e.key === 'Enter' && open && items[0]) {
              e.preventDefault();
              pick(items[0]);
            }
          }}
        />
        <span className="q-addr-state micro" aria-hidden="true">
          {busy ? m.addr.searching : m.addr.search}
        </span>
      </div>

      {open && items.length > 0 ? (
        <ul className="q-suggest" role="listbox">
          {items.map((r, i) => (
            <li key={`${r.lat},${r.lng},${i}`}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                className="q-suggest-item"
                onPointerDown={(e) => e.preventDefault()}
                onClick={() => pick(r)}
                title={r.label}
              >
                <span className="q-suggest-l">{r.label}</span>
                <span className="q-suggest-k micro">{r.kind === 'city' ? m.addr.city : m.addr.address}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {!open && searched && items.length === 0 ? (
        <p className="q-addr-none micro">{m.addr.none}</p>
      ) : null}
    </div>
  );
}
