/** 联系页文案契约：三语共用同一形状，缺字段由 tsc 直接报出来。 */

export type ContactDetail = { label: string; value: string; href?: string; pending?: boolean };

export type ContactFieldKey =
  | 'name'
  | 'company'
  | 'inquiryType'
  | 'loadingPort'
  | 'dischargePort'
  | 'weightEstimate'
  | 'details';

export type ContactCopy = {
  meta: { title: string };
  eyebrow: string;
  title: string;
  intro: string;
  detailsTitle: string;
  detailsLead: string;
  tableHead: [string, string];
  details: ContactDetail[];
  sideKicker: string;
  sideItems: string[];
  form: {
    title: string;
    lead: string;
    fields: Record<ContactFieldKey, string>;
    placeholders: Omit<Record<ContactFieldKey, string>, 'inquiryType'>;
    types: string[];
    submit: string;
    submitting: string;
    requiredNote: string;
    incompleteTitle: string;
    incompleteBody: string;
    resultTitle: string;
    docTitle: string;
    riskTitle: string;
    hsTitle: string;
    fallback: string;
    errorNote: string;
    disclaimer: string;
  };
  photo: { src: string; alt: string; caption: string };
};

/** 首页文案契约：先只覆盖 Hero，其余段落随批注逐段迁入。 */
export type HomeCopy = {
  meta: { title: string };
  hero: {
    eyebrow: string;
    titleLines: [string, string];
    lead: string;
    primary: string;
    secondary: string;
    stats: { value: string; label: string }[];
    photo: { src: string; alt: string; caption: string; index: string };
  };
};
