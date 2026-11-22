import type { AssistantCopy } from '../zh/assistant';

/** Tiếng Việt：全站悬浮测算助手。 */
const assistant: AssistantCopy = {
  suggestions: [
    'Cần chuẩn bị những hồ sơ gì để báo giá?',
    'Báo giá gồm những chi phí nào?',
    'Liên hệ bộ phận hỗ trợ bằng cách nào?',
  ],
  intro:
    'Tôi là trợ lý tư vấn, phụ trách tư vấn nghiệp vụ: phạm vi dịch vụ, quy trình tuyến Trung - Việt, chứng từ và thời gian. Muốn tính số km và cước vận chuyển, vui lòng dùng "Trợ lý báo giá" ở trang báo giá (/quote), trang đó tính theo tuyến và dữ liệu giá cước.',
  actions: {
    docDetail: 'Xem chi tiết từng mục phí',
    reMatch: 'Đổi loại xe tính lại',
    reMatchPrompt: 'Tính lại theo xe nguyên chiếc, sàn thấp 17,5 m',
    vehicleMatch: 'Mở khớp loại xe',
    submitQuote: 'Gửi yêu cầu báo giá chính thức',
  },
  status: {
    idle: 'Chưa gọi công cụ tính toán',
    reading: 'Đang phân tích câu hỏi…',
    calling: 'Đang gọi: {label}',
    callingGeneric: 'Đang gọi công cụ tính toán…',
    done: 'Công cụ tính toán đã trả kết quả',
  },
  ui: {
    clear: 'Xóa hội thoại',
    typing: 'Đang soạn…',
    placeholder: 'VD: Nam Ninh → Hà Nội, 20 tấn, xe nguyên chiếc',
    askAria: 'Hỏi trợ lý tư vấn',
    sending: 'Đang soạn…',
    send: 'Gửi',
    note: 'Tính toán sơ bộ · Không phải báo giá chính thức · Không cam kết thời gian',
  },
};

export default assistant;
