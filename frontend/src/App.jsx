import React, { createContext, useCallback, useEffect, useState } from 'react'
import { Layout, Menu, Segmented, Space, Tag, Typography } from 'antd'
import {
  DashboardOutlined, ExperimentOutlined, FieldTimeOutlined, FundOutlined,
  ProfileOutlined, SettingOutlined, StarOutlined,
} from '@ant-design/icons'
import { apiGet, Pnl, num } from './util'
import { useLang } from './i18n'
import Dashboard from './pages/Dashboard'
import Strategies from './pages/Strategies'
import Mystic from './pages/Mystic'
import Positions from './pages/Positions'
import Rounds from './pages/Rounds'
import Orders from './pages/Orders'
import Settings from './pages/Settings'

export const Ctx = createContext(null)

const PAGES = {
  dashboard: Dashboard, strategies: Strategies, mystic: Mystic,
  positions: Positions, rounds: Rounds, orders: Orders, settings: Settings,
}

const hashPage = () => window.location.hash.replace('#/', '') || 'dashboard'

export default function App() {
  const { t, lang, setLang } = useLang()
  const [state, setState] = useState(null)
  const [page, setPage] = useState(hashPage())

  const refresh = useCallback(async () => {
    try { setState(await apiGet('/api/state')) } catch { /* keep last */ }
  }, [])

  useEffect(() => {
    refresh()
    const iv = setInterval(refresh, 5000)
    return () => clearInterval(iv)
  }, [refresh])

  useEffect(() => {
    const f = () => setPage(hashPage())
    window.addEventListener('hashchange', f)
    return () => window.removeEventListener('hashchange', f)
  }, [])

  const st = state?.status
  const engineFresh = st && st.now - st.last_tick < 45
  const Page = PAGES[page] || Dashboard

  const MENU = [
    { key: 'dashboard', icon: <DashboardOutlined />, label: t('menu.dashboard') },
    { key: 'strategies', icon: <ExperimentOutlined />, label: t('menu.strategies') },
    { key: 'mystic', icon: <StarOutlined />, label: t('menu.mystic') },
    { key: 'positions', icon: <FundOutlined />, label: t('menu.positions') },
    { key: 'rounds', icon: <FieldTimeOutlined />, label: t('menu.rounds') },
    { key: 'orders', icon: <ProfileOutlined />, label: t('menu.orders') },
    { key: 'settings', icon: <SettingOutlined />, label: t('menu.settings') },
  ]

  return (
    <Ctx.Provider value={{ state, refresh }}>
      <Layout style={{ minHeight: '100vh' }}>
        <Layout.Sider width={208} breakpoint="lg" collapsedWidth={64}>
          <div style={{
            height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: 17, fontWeight: 700, letterSpacing: 0.5,
          }}>
            🎲 claw-poly
          </div>
          <Menu
            theme="dark" mode="inline" selectedKeys={[page]} items={MENU}
            onSelect={({ key }) => { window.location.hash = '#/' + key }}
          />
        </Layout.Sider>
        <Layout>
          <Layout.Header style={{
            background: '#1f1f1f', padding: '0 20px', display: 'flex',
            alignItems: 'center', justifyContent: 'space-between', height: 56,
          }}>
            <Space size="middle" wrap>
              <Tag color="blue" style={{ fontSize: 13 }}>
                {t('paper.title')}
              </Tag>
              <Typography.Text>
                BTC <Typography.Text strong style={{ fontVariantNumeric: 'tabular-nums' }}>
                  ${num(st?.btc)}
                </Typography.Text>
              </Typography.Text>
              <Typography.Text>
                {t('hdr.today')} <Pnl v={st?.realized_today} bold />
              </Typography.Text>
              {st?.halted && <Tag color="red">{t('hdr.halted')}</Tag>}
            </Space>
            <Space size="small">
              <Tag color={engineFresh ? 'success' : 'error'}>
                {engineFresh ? t('hdr.engine.ok') : t('hdr.engine.dead')}
              </Tag>
              <Tag color="cyan">{t('paper.short')}</Tag>
              <Segmented
                size="small" value={lang} onChange={setLang}
                options={[{ label: '中', value: 'zh' }, { label: 'EN', value: 'en' }]}
              />
            </Space>
          </Layout.Header>
          <Layout.Content style={{ margin: 16 }}>
            <Page />
          </Layout.Content>
        </Layout>
      </Layout>
    </Ctx.Provider>
  )
}
