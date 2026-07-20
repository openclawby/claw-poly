import React, { useContext, useEffect, useMemo, useState } from 'react'
import {
  Alert, Button, Card, Col, Divider, Form, Input, InputNumber, message, Popconfirm,
  Row, Select, Slider, Space, Switch, Tag, Tooltip, Typography,
} from 'antd'
import {
  KeyOutlined, QuestionCircleOutlined, SaveOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { Ctx } from '../App'
import { apiGet, apiPost } from '../util'
import { useLang } from '../i18n'

function ClawbyCard({ onChanged }) {
  const { t } = useLang()
  const [st, setSt] = useState(null)
  const [key, setKey] = useState('')
  const [saving, setSaving] = useState(false)

  const load = () => apiGet('/api/clawby').then(setSt).catch(() => {})
  useEffect(() => { load() }, [])

  const save = async () => {
    if (!key.trim()) { message.warning(t('cb.empty')); return }
    setSaving(true)
    try {
      await apiPost('/api/clawby', { key: key.trim() })
      message.success(t('cb.saved'))
      setKey(''); load(); onChanged()
    } catch (e) { message.error(String(e.message || e), 6) } finally { setSaving(false) }
  }

  const clear = async () => {
    try {
      await apiPost('/api/clawby', { key: 'clear' })
      message.success(t('cb.cleared')); load(); onChanged()
    } catch (e) { message.error(String(e.message || e)) }
  }

  return (
    <Card title={t('cb.title')} size="small"
      style={st && !st.configured ? { borderColor: '#d89614' } : undefined}>
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        {st?.configured ? (
          <Alert type="success" showIcon message={<Space>{t('cb.ok')}<Typography.Text code>{st.masked}</Typography.Text></Space>} />
        ) : (
          <Alert type="warning" showIcon message={t('cb.none')} />
        )}
        <Space.Compact style={{ width: '100%' }}>
          <Input.Password placeholder={t('cb.ph')} value={key}
            onChange={(e) => setKey(e.target.value)} onPressEnter={save} />
          <Button type="primary" loading={saving} onClick={save}>{t('cb.save')}</Button>
        </Space.Compact>
        <Space style={{ justifyContent: 'space-between', width: '100%' }} wrap>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('cb.hint')}{' '}
            <a href="https://openclawby.com" target="_blank" rel="noreferrer">{t('cb.reg')}</a>
          </Typography.Text>
          {st?.configured && (
            <Popconfirm title={t('cb.clear.confirm')} onConfirm={clear}
              okText={t('cb.clear')} cancelText={t('c.cancel')}>
              <Button danger size="small">{t('cb.clear')}</Button>
            </Popconfirm>
          )}
        </Space>
      </Space>
    </Card>
  )
}

function OnboardCard({ onChanged }) {
  const { t } = useLang()
  const [st, setSt] = useState(null)
  const [busy, setBusy] = useState(false)
  const [rk, setRk] = useState(null)
  const [rkInput, setRkInput] = useState('')
  const [rkSaving, setRkSaving] = useState(false)

  const load = () => {
    apiGet('/api/onboard').then(setSt).catch(() => {})
    apiGet('/api/relayer-key').then(setRk).catch(() => {})
  }
  useEffect(() => { load() }, [])

  const saveRk = async () => {
    setRkSaving(true)
    try {
      await apiPost('/api/relayer-key', { key: rkInput.trim() })
      message.success(t('ob.relayer.saved'))
      setRkInput(''); load()
    } catch (e) { message.error(String(e.message || e), 6) } finally { setRkSaving(false) }
  }

  const clearRk = async () => {
    try {
      await apiPost('/api/relayer-key', { key: 'clear' })
      message.success(t('ob.relayer.clear')); load()
    } catch (e) { message.error(String(e.message || e)) }
  }

  const run = async () => {
    setBusy(true)
    try {
      const r = await apiPost('/api/onboard', {})
      message.success(r.already ? t('ob.already') : t('ob.done', { w: r.wallet }), 8)
      load(); onChanged()
    } catch (e) { message.error(String(e.message || e), 8) } finally { setBusy(false) }
  }

  if (!st) return <Card title={t('ob.title')} size="small" loading />
  const blockers = []
  if (!st.key_ready) blockers.push(t('ob.need.key'))
  if (!st.relayer_ready) blockers.push(t('ob.need.relayer'))
  if (!st.sdk_ready) blockers.push(t('ob.need.sdk'))

  return (
    <Card title={t('ob.title')} size="small"
      style={st.ready ? undefined : { borderColor: '#d89614' }}
      extra={<Button size="small" onClick={load}>{t('ob.recheck')}</Button>}>
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        {st.ready ? (
          <Alert type="success" showIcon message={(
            <Space wrap size={4}>
              {t('ob.ready')}
              <Typography.Text code copyable style={{ fontSize: 11 }}>{st.wallet}</Typography.Text>
              <Tag color="blue">{st.wallet_type}</Tag>
              <Tag color="success">{t('ob.approved')}: {t('ob.yes')}</Tag>
            </Space>
          )} />
        ) : (
          <>
            <Alert type="warning" showIcon message={t('ob.notready')} description={t('ob.desc')} />
            {blockers.length > 0 && (
              <Space direction="vertical" size={2}>
                {blockers.map((b) => (
                  <Typography.Text key={b} type="secondary" style={{ fontSize: 12 }}>{b}</Typography.Text>
                ))}
              </Space>
            )}
            <Button type="primary" loading={busy} disabled={blockers.length > 0} onClick={run}>
              {busy ? t('ob.doing') : t('ob.btn')}
            </Button>
          </>
        )}
        <Divider style={{ margin: '4px 0' }} />
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Space size={6} wrap>
            <Typography.Text strong style={{ fontSize: 12 }}>{t('ob.relayer')}</Typography.Text>
            <Tooltip title={t('ob.relayer.hint')}>
              <QuestionCircleOutlined style={{ color: '#888' }} />
            </Tooltip>
            {rk?.configured && (
              <Tag color="success">{t('ob.relayer.ok')} <Typography.Text code style={{ fontSize: 11 }}>{rk.masked}</Typography.Text></Tag>
            )}
          </Space>
          <Space.Compact style={{ width: '100%' }}>
            <Input.Password placeholder={t('ob.relayer.ph')} value={rkInput}
              onChange={(e) => setRkInput(e.target.value)} onPressEnter={saveRk} />
            <Button loading={rkSaving} onClick={saveRk} disabled={!rkInput.trim()}>
              {t('ob.relayer.save')}
            </Button>
            {rk?.configured && (
              <Popconfirm title={t('ob.relayer.clear')} onConfirm={clearRk}
                okText={t('c.confirm')} cancelText={t('c.cancel')}>
                <Button danger>{t('ob.relayer.clear')}</Button>
              </Popconfirm>
            )}
          </Space.Compact>
        </Space>
        {st.error && <Typography.Text type="danger" style={{ fontSize: 12 }}>{st.error}</Typography.Text>}
      </Space>
    </Card>
  )
}

function WalletCard() {
  const { t } = useLang()
  const [w, setW] = useState(null)
  const [loading, setLoading] = useState(false)
  const [pullAmt, setPullAmt] = useState(null)
  const [pulling, setPulling] = useState(false)
  const [wdAmt, setWdAmt] = useState(null)
  const [sending, setSending] = useState(false)

  const load = async () => {
    setLoading(true)
    try { setW(await apiGet('/api/wallet')) } catch { /* noop */ }
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  const pull = async () => {
    setPulling(true)
    try {
      const r = await apiPost('/api/wallet/pull', { amount: pullAmt })
      message.success(t('w.pull.done', { tx: (r.tx || '').slice(0, 18) + '…' }), 8)
      setPullAmt(null); load()
    } catch (e) { message.error(String(e.message || e), 6) } finally { setPulling(false) }
  }

  const withdraw = async () => {
    setSending(true)
    try {
      const r = await apiPost('/api/wallet/withdraw', { amount: wdAmt })
      message.success(t('w.wd.done', { tx: (r.tx || '').slice(0, 18) + '…' }), 8)
      setWdAmt(null); load()
    } catch (e) { message.error(String(e.message || e), 6) } finally { setSending(false) }
  }

  if (w && !w.ready) {
    return <Card title={t('w.title')} size="small"><Alert type="warning" showIcon message={t('w.notready')} /></Card>
  }

  const legacyBal = w?.legacy_balance ?? 0
  const step = (n, text) => (
    <Space size={6} align="center">
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 20, height: 20, borderRadius: 10, background: '#1668dc',
        color: '#fff', fontSize: 12, fontWeight: 600,
      }}>{n}</span>
      <Typography.Text strong style={{ fontSize: 13 }}>{text}</Typography.Text>
    </Space>
  )

  return (
    <Card
      title={t('w.title')} size="small"
      extra={(
        <Space>
          <Typography.Text strong style={{ fontSize: 16 }}>
            {w?.balance != null ? `$${w.balance.toFixed(2)}` : '…'}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('w.balance')}</Typography.Text>
          <Button size="small" loading={loading} onClick={load}>{t('w.refresh')}</Button>
        </Space>
      )}
    >
      <Row gutter={[20, 16]}>
        {/* ---------- 充值:两步 ---------- */}
        <Col xs={24} lg={12}>
          <Typography.Title level={5} style={{ marginTop: 0 }}>⬇️ {t('w.dep.title')}</Typography.Title>
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <div>
              {step(1, t('w.dep.s1'))}
              <div style={{ marginTop: 6, paddingLeft: 26 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('w.dep.s1.desc')}</Typography.Text>
                <div style={{ marginTop: 4 }}>
                  <Button size="small" type="link" style={{ paddingLeft: 0 }}
                    href="https://polymarket.com" target="_blank" rel="noreferrer">
                    polymarket.com ↗
                  </Button>
                </div>
              </div>
            </div>
            <div>
              {step(2, t('w.dep.s2'))}
              <div style={{ marginTop: 6, paddingLeft: 26 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('w.pull.bal')}: <Typography.Text strong>${legacyBal.toFixed(2)}</Typography.Text>
                </Typography.Text>
                <Space.Compact style={{ width: '100%', marginTop: 6 }}>
                  <InputNumber
                    style={{ flex: 1 }} min={0.01} max={legacyBal || undefined} prefix="$"
                    placeholder={t('w.wd.amount')} value={pullAmt} onChange={setPullAmt}
                    disabled={!legacyBal}
                  />
                  <Button onClick={() => setPullAmt(legacyBal)} disabled={!legacyBal}>{t('w.wd.max')}</Button>
                  <Popconfirm
                    title={t('w.pull.confirm', { a: pullAmt ?? 0 })}
                    description={t('w.pull.confirm.desc', { a: pullAmt ?? 0 })}
                    onConfirm={pull} okText={t('c.confirm')} cancelText={t('c.cancel')}
                  >
                    <Button type="primary" loading={pulling} disabled={!pullAmt || !legacyBal}>
                      {t('w.pull.btn')}
                    </Button>
                  </Popconfirm>
                </Space.Compact>
                {!legacyBal && (
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>{t('w.pull.empty')}</Typography.Text>
                )}
              </div>
            </div>
            <Alert
              type="info" style={{ fontSize: 12 }}
              message={(
                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                  <Typography.Text style={{ fontSize: 12 }}>{t('w.dep.advanced')}</Typography.Text>
                  <Typography.Text code copyable style={{ fontSize: 11 }}>{w?.address}</Typography.Text>
                  <Typography.Text type="warning" style={{ fontSize: 11 }}>{t('w.dep.warn')}</Typography.Text>
                </Space>
              )}
            />
          </Space>
        </Col>

        {/* ---------- 提现:金额 -> 旧账户 ---------- */}
        <Col xs={24} lg={12}>
          <Typography.Title level={5} style={{ marginTop: 0 }}>⬆️ {t('w.wd.title')}</Typography.Title>
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <div>
              {step(1, t('w.wd.s1'))}
              <div style={{ marginTop: 6, paddingLeft: 26 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('w.wd.to.fixed')}:{' '}
                  <Typography.Text code copyable style={{ fontSize: 11 }}>{w?.legacy_address || '—'}</Typography.Text>
                </Typography.Text>
                <Space.Compact style={{ width: '100%', marginTop: 6 }}>
                  <InputNumber
                    style={{ flex: 1 }} min={0.01} max={w?.balance ?? undefined} prefix="$"
                    placeholder={t('w.wd.amount')} value={wdAmt} onChange={setWdAmt}
                  />
                  <Button onClick={() => setWdAmt(w?.balance ?? null)}>{t('w.wd.max')}</Button>
                  <Popconfirm
                    title={t('w.wd.confirm')}
                    description={<div style={{ maxWidth: 340 }}>{t('w.wd.confirm.desc2', { a: wdAmt ?? 0 })}</div>}
                    onConfirm={withdraw} okText={t('c.confirm')} cancelText={t('c.cancel')}
                    okButtonProps={{ danger: true }}
                  >
                    <Button type="primary" danger loading={sending} disabled={!wdAmt || !w?.legacy_address}>
                      {t('w.wd.btn')}
                    </Button>
                  </Popconfirm>
                </Space.Compact>
              </div>
            </div>
            <div>
              {step(2, t('w.wd.s2'))}
              <div style={{ marginTop: 6, paddingLeft: 26 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('w.wd.s2.desc')}</Typography.Text>
              </div>
            </div>
          </Space>
        </Col>
      </Row>
    </Card>
  )
}

function PrivateKeyCard({ onChanged }) {
  const { t } = useLang()
  const [status, setStatus] = useState(null)
  const [key, setKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [ctx, setCtx] = useState({ funder: '', signature_type: 0 })
  const [ctxLoaded, setCtxLoaded] = useState(false)

  const load = () => apiGet('/api/private-key').then((d) => {
    setStatus(d)
    if (!ctxLoaded) {
      setCtx({ funder: d.funder || '', signature_type: d.signature_type ?? 0 })
      setCtxLoaded(true)
    }
  }).catch(() => {})
  useEffect(() => { load() }, [])  // eslint-disable-line

  const saveCtx = async () => {
    try {
      await apiPost('/api/private-key/context', ctx)
      message.success(t('g.key.ctx.saved'))
      load()
      onChanged()
    } catch (e) { message.error(String(e.message || e)) }
  }

  const save = async () => {
    if (!key.trim()) { message.warning(t('g.key.empty')); return }
    setSaving(true)
    try {
      const r = await apiPost('/api/private-key', { key: key.trim() })
      message.success(t('g.key.saved', { a: r.address }))
      if (r.warning) message.warning(r.warning, 8)
      setKey('')
      load()
      onChanged()
    } catch (e) { message.error(String(e.message || e)) } finally { setSaving(false) }
  }

  const clear = async () => {
    try {
      await apiPost('/api/private-key', { key: 'clear' })
      message.success(t('g.key.cleared'))
      load()
      onChanged()
    } catch (e) { message.error(String(e.message || e)) }
  }

  return (
    <Card title={<Space><KeyOutlined />{t('g.key.title')}</Space>} size="small">
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        {status?.configured ? (
          <Alert
            type="success" showIcon
            message={(
              <Space wrap>
                {t('g.key.ok')} <Typography.Text code copyable>{status.address}</Typography.Text>
                {status.funder && (
                  status.match
                    ? <Tag color="success">{t('g.key.match')}</Tag>
                    : <Tag color="warning">{t('g.key.mismatch', { a: status.funder.slice(0, 8) })}</Tag>
                )}
              </Space>
            )}
          />
        ) : (
          <Alert type="warning" showIcon message={t('g.key.none')} />
        )}
        <Space.Compact style={{ width: '100%' }}>
          <Input.Password
            placeholder={t('g.key.ph')}
            value={key} onChange={(e) => setKey(e.target.value)}
            onPressEnter={save}
          />
          <Button type="primary" loading={saving} onClick={save}>{t('g.key.save')}</Button>
        </Space.Compact>
        <Row gutter={12}>
          <Col xs={24} md={11}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('g.key.funder')}{' '}
              <Tooltip title={t('g.key.funder.hint')}><QuestionCircleOutlined style={{ color: '#888' }} /></Tooltip>
            </Typography.Text>
            <Input
              placeholder="0x…" value={ctx.funder}
              onChange={(e) => setCtx({ ...ctx, funder: e.target.value })}
            />
          </Col>
          <Col xs={16} md={9}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('g.key.sig')}{' '}
              <Tooltip title={t('g.key.sig.hint')}><QuestionCircleOutlined style={{ color: '#888' }} /></Tooltip>
            </Typography.Text>
            <Select
              style={{ width: '100%' }} value={ctx.signature_type}
              onChange={(v) => setCtx({ ...ctx, signature_type: v })}
              options={[
                { value: 0, label: t('g.key.sig.0') },
                { value: 1, label: t('g.key.sig.1') },
                { value: 2, label: t('g.key.sig.2') },
                { value: 3, label: t('g.key.sig.3') },
              ]}
            />
          </Col>
          <Col xs={8} md={4} style={{ display: 'flex', alignItems: 'flex-end' }}>
            <Button block onClick={saveCtx}>{t('g.key.ctx.save')}</Button>
          </Col>
        </Row>
        {(ctx.signature_type === 1 || ctx.signature_type === 2 || ctx.signature_type === 3) && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>ℹ️ {t('g.key.proxy.note')}</Typography.Text>
        )}
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('g.key.note')}
          </Typography.Text>
          {status?.configured && (
            <Popconfirm title={t('g.key.clear.confirm')} onConfirm={clear} okText={t('g.key.clear.ok')} cancelText={t('c.cancel')}>
              <Button danger size="small">{t('g.key.clear')}</Button>
            </Popconfirm>
          )}
        </Space>
      </Space>
    </Card>
  )
}

export default function Settings() {
  const { t } = useLang()
  const { state, refresh } = useContext(Ctx)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const raw = state?.settings

  const initial = useMemo(() => {
    if (!raw) return null
    return {
      take_profit_pct: Number(raw.take_profit_pct),
      horizon: Number(raw.horizon),
      daily_loss_halt_usd: Number(raw.daily_loss_halt_usd),
      max_open_usd: Number(raw.max_open_usd),
      overpay_cap: Number(raw.overpay_cap),
    }
  }, [raw])

  // fill the form once; later polls must not clobber in-progress edits
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    if (initial && !loaded) {
      form.setFieldsValue(initial)
      setLoaded(true)
    }
  }, [initial, loaded, form])

  if (!raw) return <Card loading />

  const live = raw.live_enabled === '1'
  const liveReady = state?.status?.live_ready

  const label = (text, hint) => (
    <Space size={4}>
      {text}
      {hint && <Tooltip title={hint}><QuestionCircleOutlined style={{ color: '#888' }} /></Tooltip>}
    </Space>
  )

  const onSave = async () => {
    try {
      const v = await form.validateFields()
      setSaving(true)
      await apiPost('/api/settings', {
        take_profit_pct: String(v.take_profit_pct),
        horizon: String(v.horizon),
        daily_loss_halt_usd: String(v.daily_loss_halt_usd),
        max_open_usd: String(v.max_open_usd),
        overpay_cap: String(v.overpay_cap),
      })
      message.success(t('g.saved'))
      refresh()
    } catch (e) {
      if (e?.errorFields) return
      message.error(String(e.message || e))
    } finally { setSaving(false) }
  }

  const toggleRedeem = async (on) => {
    try {
      await apiPost('/api/settings', { auto_redeem: on ? '1' : '0' })
      message.success(on ? t('g.redeem.on') : t('g.redeem.off'))
      refresh()
    } catch (e) { message.error(String(e.message || e)) }
  }

  const toggleLive = async (on) => {
    try {
      await apiPost('/api/settings', { live_enabled: on ? '1' : '0' })
      message.success(on ? t('g.live.on.msg') : t('g.live.off.msg'))
      refresh()
    } catch (e) { message.error(String(e.message || e)) }
  }

  return (
    <Form form={form} layout="vertical" initialValues={initial || {}}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <ClawbyCard onChanged={refresh} />

        <OnboardCard onChanged={refresh} />

        <Alert type="info" showIcon message={t('g.moved')} />
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card title={t('g.trade')}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="take_profit_pct" rules={[{ required: true }]} label={label(t('g.tp'), t('g.tp.hint'))}>
                    <InputNumber min={1} max={500} style={{ width: '100%' }} suffix="%" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="horizon" rules={[{ required: true }]} label={label(t('g.horizon'), t('g.horizon.hint'))}>
                    <InputNumber min={1} max={6} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title={t('g.risk')}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="daily_loss_halt_usd" rules={[{ required: true }]} label={label(t('g.halt'), t('g.halt.hint'))}>
                    <InputNumber min={0} style={{ width: '100%' }} prefix="$" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="max_open_usd" rules={[{ required: true }]} label={label(t('g.maxopen'), t('g.maxopen.hint'))}>
                    <InputNumber min={0} style={{ width: '100%' }} prefix="$" />
                  </Form.Item>
                </Col>
                <Col span={24}>
                  <Form.Item name="overpay_cap" label={label(t('g.overpay'), t('g.overpay.hint'))}>
                    <Slider min={0.5} max={0.99} step={0.01} marks={{ 0.5: '0.50', 0.85: '0.85', 0.99: '0.99' }} />
                  </Form.Item>
                </Col>
              </Row>
            </Card>
          </Col>
        </Row>

        <WalletCard />

        <PrivateKeyCard onChanged={refresh} />

        <Card title={t('g.live.title')} size="small">
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            {liveReady ? (
              <Alert
                type={live ? 'error' : 'success'} showIcon
                message={live ? t('g.live.on') : t('g.live.ready')}
                description={live ? t('g.live.on.desc') : t('g.live.ready.desc')}
              />
            ) : (
              <Alert type="warning" showIcon message={t('g.live.notready')} />
            )}
            <Space>
              <Switch checked={raw.auto_redeem !== '0'} onChange={toggleRedeem} />
              <Typography.Text>{t('g.redeem')}</Typography.Text>
              <Tooltip title={t('g.redeem.hint')}>
                <QuestionCircleOutlined style={{ color: '#888' }} />
              </Tooltip>
            </Space>
            <Popconfirm
              title={live ? t('g.live.turnoff') : t('g.live.turnon')}
              description={live ? t('g.live.turnoff.desc') : t('g.live.turnon.desc')}
              onConfirm={() => toggleLive(!live)}
              okText={t('c.confirm')} cancelText={t('c.cancel')} okButtonProps={{ danger: !live }}
            >
              <Button danger={!live} type={live ? 'default' : 'primary'} icon={<ThunderboltOutlined />} disabled={!liveReady && !live}>
                {live ? t('g.live.btn.off') : t('g.live.btn.on')}
              </Button>
            </Popconfirm>
          </Space>
        </Card>

        <Space.Compact block>
          <Button type="primary" size="large" icon={<SaveOutlined />} onClick={onSave} loading={saving} style={{ width: '75%' }}>
            {t('g.saveall')}
          </Button>
          <Button size="large" style={{ width: '25%' }} onClick={() => { form.setFieldsValue(initial); message.info(t('g.reset.msg')) }}>
            {t('g.reset')}
          </Button>
        </Space.Compact>
      </Space>
    </Form>
  )
}
