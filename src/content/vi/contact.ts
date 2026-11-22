import type { ContactCopy } from '../types';

/** Tiếng Việt：沿用旧站 src/main.tsx translations.vi 已审的 contact / consult 文案，不重译。 */
export const contact: ContactCopy = {
  meta: { title: 'Liên hệ & Báo giá | JIUNENG logistics' },
  eyebrow: 'Liên hệ & Báo giá',
  title: 'Gửi hồ sơ dự án, chúng ta cùng hoàn thiện phương án',
  intro: 'Phù hợp gửi packing list, bản vẽ thiết bị, bảng kích thước trọng lượng, địa chỉ đích, thời gian giao và trạng thái chứng từ.',
  detailsTitle: 'Thông tin liên hệ',
  detailsLead: 'Quản lý dự án phản hồi trực tiếp trong ngày làm việc; dự án gấp vui lòng gọi điện thêm.',
  tableHead: ['Nội dung', 'Thông tin'],
  details: [
    { label: 'Email', value: 'jiuneng.vn@gmail.com', href: 'mailto:jiuneng.vn@gmail.com' },
    { label: 'Hotline Trung Quốc', value: '15687419919', href: 'tel:+8615687419919' },
    { label: 'Văn phòng Hà Nội', value: 'R03, Tầng 5, Số 82 phố Duy Tân, Phường Cầu Giấy, Hà Nội' },
    { label: 'WeChat / WhatsApp', value: 'Đang cập nhật', pending: true },
  ],
  sideKicker: 'Nên gửi kèm khi yêu cầu báo giá',
  sideItems: [
    'Packing list và bản vẽ thiết bị',
    'Bảng kích thước, trọng lượng (kích thước lớn nhất mỗi kiện)',
    'Địa chỉ điểm đến và điều kiện xếp dỡ tại hiện trường',
    'Thời gian giao hàng và trạng thái chứng từ',
  ],
  form: {
    title: 'Gửi nhu cầu dự án',
    lead: 'Sau khi gửi, hệ thống sắp xếp đánh giá ban đầu; quản lý dự án kiểm tra rồi đưa ra phương án chính thức.',
    fields: {
      name: 'Người liên hệ',
      company: 'Công ty',
      inquiryType: 'Loại nghiệp vụ',
      loadingPort: 'Điểm đi',
      dischargePort: 'Điểm đến',
      weightEstimate: 'Trọng lượng / thể tích',
      details: 'Chi tiết dự án',
    },
    placeholders: {
      name: 'Nhập họ tên',
      company: 'Tên công ty hoặc dự án',
      loadingPort: 'VD: nhà máy Phật Sơn / cảng Thâm Quyến / cửa khẩu Bằng Tường',
      dischargePort: 'VD: Hà Nội / Hải Phòng / TP.HCM',
      weightEstimate: 'VD: 18 tấn, dài 12m, rộng 3.2m',
      details: 'Mô tả hàng hóa, số kiện, kích thước, thời hạn và yêu cầu đặc biệt',
    },
    types: ['Logistics công trình', 'Khai quan XNK', 'Thương mại quốc tế', 'Tư vấn giải pháp'],
    submit: 'Gửi yêu cầu',
    submitting: 'Đang tạo đánh giá',
    requiredNote: 'Người liên hệ và chi tiết dự án là bắt buộc, các mục còn lại có thể để trống.',
    incompleteTitle: 'Cần bổ sung hai mục',
    incompleteBody:
      'Vui lòng điền người liên hệ và chi tiết dự án; các mục còn lại có thể để trống, quản lý dự án sẽ bổ sung qua điện thoại hoặc email.',
    resultTitle: 'Đánh giá ban đầu',
    docTitle: 'Chứng từ có thể liên quan',
    riskTitle: 'Cần xác nhận trước',
    hsTitle: 'Hướng phân loại và thuế',
    fallback:
      'Đã nhận nhu cầu. Bước tiếp theo nên bổ sung kích thước, trọng lượng, thời gian xếp hàng, mã HS và điều kiện hiện trường để quản lý dự án xác nhận tuyến, loại xe và chứng từ.',
    errorNote:
      'Đánh giá trực tuyến tạm thời không khả dụng. Vui lòng gửi hồ sơ đến jiuneng.vn@gmail.com hoặc gọi 15687419919 để quản lý dự án theo dõi.',
    disclaimer: 'Đánh giá ban đầu chỉ để sắp xếp thông tin, không phải báo giá hay cam kết thời gian.',
  },
  photo: {
    src: '/assets/v8/contact-lowbed.jpg',
    alt: 'Xe sàn thấp nhiều trục màu đỏ chở máy biến áp lớn đỗ trước nhà xưởng',
    caption: 'Xe sàn thấp nhiều trục chở máy biến áp · Hiện trường Việt Nam',
  },
};

export default contact;
