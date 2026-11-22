import type { ContactCopy } from '../types';

/** English: reuses the reviewed copy from the old site's src/main.tsx translations.en. */
export const contact: ContactCopy = {
  meta: { title: 'Contact & Inquiry | JIUNENG logistics' },
  eyebrow: 'Contact & inquiry',
  title: 'Send the project files and we will firm up the plan together',
  intro: 'Useful files: packing lists, equipment drawings, dimension and weight sheets, destination address, delivery timing, and document status.',
  detailsTitle: 'Contact details',
  detailsLead: 'A project manager replies directly during working hours; for urgent projects please also call.',
  tableHead: ['Item', 'Details'],
  details: [
    { label: 'Email', value: 'jiuneng.vn@gmail.com', href: 'mailto:jiuneng.vn@gmail.com' },
    { label: 'China hotline', value: '15687419919', href: 'tel:+8615687419919' },
    { label: 'Hanoi office', value: 'R03, 5th Floor, 82 Duy Tan St., Cau Giay Ward, Hanoi' },
    { label: 'WeChat / WhatsApp', value: 'Coming soon', pending: true },
  ],
  sideKicker: 'Please include with your inquiry',
  sideItems: [
    'Packing list and equipment drawings',
    'Dimension and weight sheet (largest single piece)',
    'Destination address and on-site handling conditions',
    'Delivery timing and document status',
  ],
  form: {
    title: 'Submit project needs',
    lead: 'After submission the system structures an initial assessment; a project manager reviews it and issues the formal plan.',
    fields: {
      name: 'Contact name',
      company: 'Company',
      inquiryType: 'Business type',
      loadingPort: 'Origin',
      dischargePort: 'Destination',
      weightEstimate: 'Weight / volume',
      details: 'Project details',
    },
    placeholders: {
      name: 'Enter your name',
      company: 'Company or project name',
      loadingPort: 'E.g. Foshan factory / Shenzhen port / Pingxiang border gate',
      dischargePort: 'E.g. Hanoi / Haiphong / HCMC',
      weightEstimate: 'E.g. 18 tons, 12m long, 3.2m wide',
      details: 'Describe cargo, pieces, dimensions, timeline, and special requirements',
    },
    types: ['Engineering logistics', 'Import-export customs', 'International trade', 'Solution consulting'],
    submit: 'Submit inquiry',
    submitting: 'Generating assessment',
    requiredNote: 'Contact name and project details are required; other fields can be left blank.',
    incompleteTitle: 'Two items are still missing',
    incompleteBody:
      'Please fill in the contact name and project details; other fields can be left blank and the project manager will complete them by phone or email.',
    resultTitle: 'Initial assessment',
    docTitle: 'Documents that may apply',
    riskTitle: 'Confirm in advance',
    hsTitle: 'Classification and duty direction',
    fallback:
      'Request received. Next, please add cargo dimensions, weight, loading time, HS code, and destination site conditions so the project manager can confirm route, vehicle type, and document path.',
    errorNote:
      'Online assessment is temporarily unavailable. Please send the files to jiuneng.vn@gmail.com or call 15687419919 and a project manager will follow up.',
    disclaimer: 'The initial assessment only structures communication and is not a formal quote or time commitment.',
  },
  photo: {
    src: '/assets/v8/contact-lowbed.jpg',
    alt: 'Red multi-axle low-bed trailer carrying a large transformer parked in a factory yard',
    caption: 'Multi-axle low-bed with transformer · Vietnam site',
  },
};

export default contact;
