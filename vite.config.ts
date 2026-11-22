import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';
import {defineConfig} from 'vite';

// 原始素材库（public/assets/真实项目图片，约 77MB 未压缩原图）是给「接图」用的资料源，
// 不该进 dist：真正上线的是 public/assets/ 下按规格压好的 JPEG。没有这一步，
// 每次构建都会把这几十 MB 原图一起拷进产物，Render 部署包和首字节都被拖慢。
const RAW_LIBRARY = path.resolve(__dirname, 'dist/assets/真实项目图片');

export default defineConfig(() => {
  return {
    plugins: [
      react(),
      tailwindcss(),
      {
        name: 'exclude-raw-photo-library',
        closeBundle() {
          fs.rmSync(RAW_LIBRARY, {recursive: true, force: true});
        },
      },
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    build: {
      rollupOptions: {
        input: {
          main: path.resolve(__dirname, 'index.html'),
          ai: path.resolve(__dirname, 'ai.html'),
          platform: path.resolve(__dirname, 'platform.html'),
          'platform-routing': path.resolve(__dirname, 'platform-routing.html'),
          'platform-customs': path.resolve(__dirname, 'platform-customs.html'),
          'platform-fleet': path.resolve(__dirname, 'platform-fleet.html'),
          'platform-assistant': path.resolve(__dirname, 'platform-assistant.html'),
          services: path.resolve(__dirname, 'services.html'),
          projects: path.resolve(__dirname, 'projects.html'),
          about: path.resolve(__dirname, 'about.html'),
          contact: path.resolve(__dirname, 'contact.html'),
          quote: path.resolve(__dirname, 'quote.html'),
        },
      },
    },
    server: {
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modifyâfile watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Disable file watching when DISABLE_HMR is true to save CPU during agent edits.
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
    },
  };
});
