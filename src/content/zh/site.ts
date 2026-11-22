/**
 * 中文基线：直接复用 src/site/content.ts（原有已审文案，不复制、不重写）。
 * vi / en 走同形状的独立文件；改中文只改 src/site/content.ts，改译文只改对应语言文件。
 */
import {
  about,
  cases,
  categoryPage,
  labels,
  photoCats,
  platform,
  services,
  solutions,
  tagline,
  tools,
  vehicles,
  videoStrip,
} from '../../site/content';

export const site = {
  about,
  cases,
  categoryPage,
  labels,
  photoCats,
  platform,
  services,
  solutions,
  tagline,
  tools,
  vehicles,
  videoStrip,
};

export default site;
export type SiteCopy = typeof site;
