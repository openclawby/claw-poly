import React, { useContext, useEffect, useMemo, useState } from 'react'
import {
  Alert, Button, Card, Col, Form, Input, InputNumber, message, Popconfirm,
  Row, Select, Slider, Space, Switch, Tag, Tooltip, Typography,
} from 'antd'
import {
  KeyOutlined, QuestionCircleOutlined, SaveOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { Ctx } from '../App'
import { apiGet, apiPost } from '../util'
import { useLang } from '../i18n'

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
              ]}
            />
          </Col>
          <Col xs={8} md={4} style={{ display: 'flex', alignItems: 'flex-end' }}>
            <Button block onClick={saveCtx}>{t('g.key.ctx.save')}</Button>
          </Col>
        </Row>
        {(ctx.signature_type === 1 || ctx.signature_type === 2) && (
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
