import React, { useContext, useEffect, useMemo, useState } from 'react'
import {
  Alert, Button, Card, Col, Form, InputNumber, message, Row, Slider, Space,
  Tooltip,
} from 'antd'
import { QuestionCircleOutlined, SaveOutlined } from '@ant-design/icons'
import { Ctx } from '../App'
import { apiPost } from '../util'
import { useLang } from '../i18n'

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

  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    if (initial && !loaded) {
      form.setFieldsValue(initial)
      setLoaded(true)
    }
  }, [initial, loaded, form])

  if (!raw) return <Card loading />

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

  return (
    <Form form={form} layout="vertical" initialValues={initial || {}}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="success" showIcon
          message={t('paper.title')}
          description={t('paper.desc')}
        />
        <Alert type="info" showIcon message={t('g.moved')} />
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card title={t('g.trade')}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="take_profit_pct" rules={[{ required: true }]} label={label(t('g.tp'), t('g.tp.hint'))}>
                    <InputNumber min={0} max={500} style={{ width: '100%' }} suffix="%" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="horizon" rules={[{ required: true }]} label={label(t('g.horizon'), t('g.horizon.hint'))}>
                    <InputNumber min={1} max={100} precision={0} style={{ width: '100%' }} />
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
                    <InputNumber min={0} max={100000} style={{ width: '100%' }} prefix="$" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="max_open_usd" rules={[{ required: true }]} label={label(t('g.maxopen'), t('g.maxopen.hint'))}>
                    <InputNumber min={0} max={100000} style={{ width: '100%' }} prefix="$" />
                  </Form.Item>
                </Col>
                <Col span={24}>
                  <Form.Item name="overpay_cap" label={label(t('g.overpay'), t('g.overpay.hint'))}>
                    <Slider min={0.01} max={0.99} step={0.01} marks={{ 0.01: '0.01', 0.5: '0.50', 0.99: '0.99' }} />
                  </Form.Item>
                </Col>
              </Row>
            </Card>
          </Col>
        </Row>

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
