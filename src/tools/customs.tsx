import { mountPage } from '../shell/mount';
import '../styles/tools.css';
import CustomsForm from './CustomsForm';
import AssistantLauncher from './AssistantLauncher';
import { ToolHeader } from './parts';

function Customs() {
  return (
    <>
      <ToolHeader
        index="平台 02 / 报关与税费"
        title="报关与税费"
        lead="中国出口报关与越南进口清关两端费用，先给区间；需要看分项时留下公司与联系人，同一页展开明细。"
        aside={
          <p className="t-hero-note">
            公开页只给区间：分项金额属对外含服务口径，正式报价以项目经理复核为准。
          </p>
        }
      />

      <div className="t-section">
        <CustomsForm />
      </div>

      <nav className="t-cross" aria-label="其他工具">
        <p className="micro">继续</p>
        <ul>
          <li>
            <a href="/platform/routing">01 线路与运价测算 →</a>
          </li>
          <li>
            <a href="/platform/fleet">03 车辆匹配与超限 →</a>
          </li>
          <li>
            <a href="/platform/assistant">04 测算助手 →</a>
          </li>
        </ul>
      </nav>

      <AssistantLauncher />
    </>
  );
}

mountPage(<Customs />);
