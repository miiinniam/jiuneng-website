import { mountPage } from '../shell/mount';
import '../styles/tools.css';
import RoutingForm from './RoutingForm';
import AssistantLauncher from './AssistantLauncher';
import { ToolHeader } from './parts';

function Routing() {
  return (
    <>
      <ToolHeader
        index="平台 01 / 线路测算"
        title="线路与运价测算"
        lead="选起点与终点，填货重与体积，得到中越陆运里程、预计行驶时长、所需车数和参考运费区间。区间来自站内测算引擎，不是报价。"
        aside={
          <p className="t-hero-note">
            可测城市为固定清单（中国 9 个、越南 5 个）；清单外地址请走<a href="/contact">在线询价</a>。
          </p>
        }
      />

      <div className="t-section">
        <RoutingForm />
      </div>

      <nav className="t-cross" aria-label="其他工具">
        <p className="micro">继续</p>
        <ul>
          <li>
            <a href="/platform/customs">02 报关与税费 →</a>
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

mountPage(<Routing />);
