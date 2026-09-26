/**
 * 素材清单读取层。
 *
 * 清单 `assets.manifest.json` 由 `npm run assets:scan` 扫描 public/assets/agent/ 生成，
 * 构建时静态打进包里（不是运行时 fetch）—— 这样：
 *   1. 素材没到位时不会产生 404，也不会出现"破图"或布局跳动；
 *   2. 素材到位后重新 scan + build，页面自动从纯文字版式切换成有画面的版式。
 *
 * 形式：动效一律「透明底循环 MP4 + 同名 PNG 首帧（poster）」，
 * 与参照站 oneaix 的做法一致（autoplay / muted / loop / playsinline）。
 */
import raw from './assets.manifest.json';

export type MediaSlot = { video: string | null; poster: string | null };

export type AgentAssets = {
  roles: Record<string, string>;
  services: Record<string, MediaSlot>;
  apps: Record<string, MediaSlot>;
  brain: string | null;
  heroLoop: string | null;
  ctaLoop: string | null;
  /** 复用 public/assets/ 里既有的自有实景照片（case1/case2/case3/platform…） */
  photos: Record<string, string>;
};

const EMPTY: AgentAssets = {
  roles: {},
  services: {},
  apps: {},
  brain: null,
  heroLoop: null,
  ctaLoop: null,
  photos: {},
};

export const agentAssets: AgentAssets = { ...EMPTY, ...(raw as Partial<AgentAssets>) };

/** 该槽位是否有任何可用素材（决定版式要不要切成"带图"的形态） */
export function hasSlot(slot?: MediaSlot | null): boolean {
  return Boolean(slot && (slot.video || slot.poster));
}
