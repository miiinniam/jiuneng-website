/**
 * 向导共用表单原件 —— 瑞士编辑风：零圆角、无阴影、只留发丝线与字阶。
 * 只用 .q- 前缀类名（CONTRACT §7），不引用别的段的 .tool-* / .cat-*。
 */
import type { ReactNode } from 'react';

/* ────────────────────────── 字段容器 ────────────────────────── */

export function QField({
  label,
  hint,
  error,
  required,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="q-field">
      <p className="q-field-label micro">
        <span>
          {label}
          {required ? (
            <span className="q-req" aria-hidden="true">
              *
            </span>
          ) : null}
        </span>
        {hint ? <span className="q-field-hint">{hint}</span> : null}
      </p>
      {children}
      {error ? <p className="q-field-error">{error}</p> : null}
    </div>
  );
}

/* ────────────────────────── 输入 ────────────────────────── */

/** 只保留数字与小数点：避免 type=number 的滚轮/箭头副作用，交上去仍是字符串 */
function digitsOnly(v: string): string {
  return v.replace(/[^\d.]/g, '');
}

export function QInput({
  value,
  onChange,
  placeholder,
  kind = 'number',
  id,
  ariaLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  kind?: 'number' | 'text';
  id?: string;
  ariaLabel?: string;
}) {
  return (
    <input
      className="q-input"
      id={id}
      aria-label={ariaLabel}
      type="text"
      inputMode={kind === 'number' ? 'decimal' : undefined}
      autoComplete="off"
      spellCheck={false}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(kind === 'number' ? digitsOnly(e.target.value) : e.target.value)}
    />
  );
}

export function QSelect({
  value,
  onChange,
  options,
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <select
      className="q-select"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {placeholder ? <option value="">{placeholder}</option> : null}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/* ────────────────────────── 分段选择 ────────────────────────── */

export function QChoice<T extends string>({
  label,
  value,
  options,
  onChange,
  error,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; hint?: string }[];
  onChange: (v: T) => void;
  error?: string;
}) {
  return (
    <fieldset className="q-field q-fieldset">
      <legend className="q-field-label micro">{label}</legend>
      <div className="q-choice">
        {options.map((o) => {
          const on = o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              className={`q-choice-btn${on ? ' is-on' : ''}`}
              aria-pressed={on}
              onClick={() => onChange(o.value)}
            >
              <span className="q-choice-t">{o.label}</span>
              {o.hint ? <span className="q-choice-h">{o.hint}</span> : null}
            </button>
          );
        })}
      </div>
      {error ? <p className="q-field-error">{error}</p> : null}
    </fieldset>
  );
}

/* ────────────────────────── 单位切换 ────────────────────────── */

export function QUnit({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="q-unit" role="group" aria-label="重量单位">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={`q-unit-btn${o.value === value ? ' is-on' : ''}`}
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ────────────────────────── 开关 ────────────────────────── */

export function QSwitch({
  checked,
  onChange,
  label,
  desc,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  desc?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      className={`q-switch${checked ? ' is-on' : ''}`}
      onClick={() => onChange(!checked)}
    >
      <span className="q-switch-box" aria-hidden="true">
        {checked ? '✓' : ''}
      </span>
      <span className="q-switch-body">
        <span className="q-switch-l">{label}</span>
        {desc ? <span className="q-switch-d">{desc}</span> : null}
      </span>
    </button>
  );
}

export function QSwitchList({ children }: { children: ReactNode }) {
  return <div className="q-switch-list">{children}</div>;
}
