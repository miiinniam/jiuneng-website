import { mountPage } from '../shell/mount';
import '../styles/tools.css';
import AssistantLauncher, { AssistantChat } from './AssistantLauncher';
import { Disclaim, ToolHeader } from './parts';

function AssistantPage() {
  return (
    <>
      <ToolHeader
        index="平台 04 / 测算助手"
        title="测算助手"
        lead="问线路里程、车型建议、报关需要哪些单证、报价前要准备什么。助手只调站内三个工具，只给区间与口径。"
        aside={<p className="t-hero-note">不做报价、不承诺时效，也不给内部成本结构。</p>}
      />

      <div className="t-section">
        <div className="t-assistant">
          <section className="t-assistant-main">
            <div className="t-out-head">
              <p className="micro">对话</p>
              <h2 className="t-h2">描述你的货与线路</h2>
            </div>
            <AssistantChat variant="page" />
          </section>

          <aside className="t-assistant-side">
            <p className="t-label">它能做什么</p>
            <ul className="t-list">
              <li>按线路给出里程、预计行驶时长、所需车数与参考区间</li>
              <li>解释拼车与整车的差别，以及各自的必填参数</li>
              <li>梳理中国出口报关与越南进口清关的单证方向</li>
            </ul>

            <p className="t-label">它不做什么</p>
            <ul className="t-list">
              <li>不出正式报价、不承诺船期与车期</li>
              <li>不展示内部成本、利润与分项费用构成</li>
              <li>地址不在清单内时如实说查不到，不猜坐标</li>
            </ul>

            <Disclaim />

            <p className="t-hint">
              需要书面价格，把条件带到<a href="/contact">在线询价</a>，项目经理按实际核算。
            </p>
          </aside>
        </div>
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
            <a href="/platform/fleet">03 车辆匹配与超限 →</a>
          </li>
        </ul>
      </nav>

      <AssistantLauncher />
    </>
  );
}

mountPage(<AssistantPage />);
