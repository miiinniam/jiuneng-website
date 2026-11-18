import { mountPage } from '../shell/mount';
import '../styles/tools.css';
import FleetForm from './FleetForm';
import AssistantLauncher from './AssistantLauncher';
import { ToolHeader } from './parts';

function Fleet() {
  return (
    <>
      <ToolHeader
        index="平台 03 / 车辆匹配"
        title="车辆匹配与超限核查"
        lead="按单件长宽与重量给出建议车型、所需车数与拆分建议，并判定是否触发超限。超限货物不在线上直接出方案。"
        aside={<p className="t-hero-note">判定依据为单件最大尺寸；实际车辆可用性以项目经理确认为准。</p>}
      />

      <div className="t-section">
        <FleetForm />
      </div>

      <nav className="t-cross" aria-label="其他工具">
        <p className="micro">继续</p>
        <ul>
          <li>
            <a href="/platform/routing">01 线路与运价测算 →</a>
          </li>
          <li>
            <a href="/platform/customs">02 报关与税费 →</a>
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

mountPage(<Fleet />);
