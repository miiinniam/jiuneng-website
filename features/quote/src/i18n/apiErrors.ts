/** /quote API 错误文案（中 / 越 / 英）；服务端 reason 与英文透传统一兜成本地语言。 */
import type { Lang } from './strings';

type Dict = { reason: Record<string, string>; server: string; rejected: string };

const ZH: Dict = {
  reason: {
    unauthorized: '内部口令不正确或已过期，请重新输入',
    internal_disabled: '内部版暂未开启（服务端未配置口令），请稍后再试',
    engine_not_configured: '报价引擎尚未配置，暂时无法出价，请直接联系我们',
    engine_timeout: '报价引擎响应超时，请稍后重试',
    engine_error: '报价引擎返回异常，请稍后重试',
    engine_unreachable: '报价引擎连接失败，请稍后重试',
    bad_request: '报价参数不正确，请检查起终点与货物信息',
    route_not_found: '没有找到可用路线，请检查起终点或换一个地址',
    no_route: '没有找到可用路线，请检查起终点或换一个地址',
    ai_unavailable: 'AI 助手暂时不可用，请稍后再试',
    network: '网络连接失败，请检查网络后重试',
    timeout: '请求超时，请稍后重试',
    bad_response: '服务返回的数据格式不正确，请稍后重试',
    unknown: '请求失败，请稍后重试',
  },
  server: '服务暂时不可用，请稍后重试',
  rejected: '请求未被接受，请检查填写内容后重试',
};

const VI: Dict = {
  reason: {
    unauthorized: 'Mật lệnh nội bộ không đúng hoặc đã hết hạn, vui lòng nhập lại',
    internal_disabled: 'Bản nội bộ chưa mở (máy chủ chưa cấu hình mật lệnh), vui lòng thử lại sau',
    engine_not_configured: 'Công cụ báo giá chưa được cấu hình, tạm thời không thể báo giá, vui lòng liên hệ trực tiếp',
    engine_timeout: 'Công cụ báo giá phản hồi quá lâu, vui lòng thử lại sau',
    engine_error: 'Công cụ báo giá trả về lỗi, vui lòng thử lại sau',
    engine_unreachable: 'Không kết nối được công cụ báo giá, vui lòng thử lại sau',
    bad_request: 'Thông số báo giá không đúng, vui lòng kiểm tra điểm đi/đến và thông tin hàng hóa',
    route_not_found: 'Không tìm thấy tuyến khả dụng, vui lòng kiểm tra điểm đi/đến hoặc đổi địa chỉ',
    no_route: 'Không tìm thấy tuyến khả dụng, vui lòng kiểm tra điểm đi/đến hoặc đổi địa chỉ',
    ai_unavailable: 'Trợ lý AI tạm thời không khả dụng, vui lòng thử lại sau',
    network: 'Kết nối mạng thất bại, vui lòng kiểm tra mạng và thử lại',
    timeout: 'Yêu cầu quá thời gian, vui lòng thử lại sau',
    bad_response: 'Dữ liệu dịch vụ trả về sai định dạng, vui lòng thử lại sau',
    unknown: 'Yêu cầu thất bại, vui lòng thử lại sau',
  },
  server: 'Dịch vụ tạm thời không khả dụng, vui lòng thử lại sau',
  rejected: 'Yêu cầu không được tiếp nhận, vui lòng kiểm tra nội dung đã điền và thử lại',
};

const EN: Dict = {
  reason: {
    unauthorized: 'The internal passphrase is wrong or expired; please enter it again',
    internal_disabled: 'The internal version is not enabled (no passphrase configured on the server); please retry later',
    engine_not_configured: 'The quoting engine is not configured, so pricing is unavailable; please contact us directly',
    engine_timeout: 'The quoting engine timed out; please retry shortly',
    engine_error: 'The quoting engine returned an error; please retry shortly',
    engine_unreachable: 'Could not connect to the quoting engine; please retry shortly',
    bad_request: 'Quote parameters are invalid; please check origin, destination and cargo details',
    route_not_found: 'No usable route found; please check the endpoints or try another address',
    no_route: 'No usable route found; please check the endpoints or try another address',
    ai_unavailable: 'The AI assistant is temporarily unavailable; please retry shortly',
    network: 'Network connection failed; please check your connection and retry',
    timeout: 'Request timed out; please retry shortly',
    bad_response: 'The service returned data in an unexpected format; please retry shortly',
    unknown: 'Request failed; please retry shortly',
  },
  server: 'The service is temporarily unavailable; please retry shortly',
  rejected: 'The request was not accepted; please check what you entered and retry',
};

export function apiErrors(lang: Lang): Dict {
  if (lang === 'vi') return VI;
  if (lang === 'en') return EN;
  return ZH;
}
