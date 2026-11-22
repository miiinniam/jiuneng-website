import type { HomeCopy } from '../types';

/** Tiếng Việt：Hero 沿用旧站 translations.vi.hero 的已审措辞（长句按语义断成两行标题）。 */
export const home: HomeCopy = {
  meta: { title: 'JIUNENG logistics | Nền tảng logistics công trình' },
  hero: {
    eyebrow: 'Logistics công trình · Khai quan · Thương mại quốc tế',
    titleLines: ['Nền tảng logistics công trình', 'cho doanh nghiệp Trung Quốc'],
    lead: 'JIUNENG tập trung vào logistics công trình, khai quan và thương mại quốc tế, quản lý báo giá, thiết kế phương án, thực hiện và bàn giao dự án bằng hệ thống số, kết nối nguồn lực hai bên Trung - Việt cho các dự án công trình phức tạp.',
    primary: 'Báo giá trực tuyến',
    secondary: 'Xem dự án',
    stats: [
      { value: 'CN-VN', label: 'Phối hợp Trung - Việt' },
      { value: '3', label: 'Logistics · Khai quan · Thương mại' },
      { value: 'Đường sắt·Điện gió·Điện', label: 'Giải pháp công trình' },
      { value: '2024', label: 'Đăng ký tại Việt Nam' },
    ],
    photo: {
      src: '/assets/v8/hero-blade-convoy.jpg',
      alt: 'Vận chuyển cánh turbine gió trên đường núi, có hộ tống và bảo đảm tuyến đường',
      caption: 'Cánh turbine gió trên đường núi · Hộ tống hiện trường',
      index: '01 / Hiện trường',
    },
  },
};

export default home;
