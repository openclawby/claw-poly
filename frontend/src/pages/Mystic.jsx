import React, { useEffect, useState } from 'react'
import {
  Alert, Button, Card, Col, DatePicker, Descriptions, Divider, Input,
  InputNumber, message, Popconfirm, Progress, Row, Segmented, Space, Table,
  Tag, Tooltip, Typography,
} from 'antd'
import { QuestionCircleOutlined, ThunderboltOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { apiGet, apiPost, fmtTs, Pnl, SideTag } from '../util'
import { useLang } from '../i18n'

export default function Mystic() {
  const { t, lang } = useLang()
  const [data, setData] = useState(null)
  const [form, setForm] = useState({
    name: '', birth: '1995-06-15', gender: '男', birthplace: '',
    count: 50, usd: 1, max_price: 0.55, tp_mode: 'settle', tp_price: 0.8,
  })
  const [starting, setStarting] = useState(false)

  const load = () => apiGet('/api/mystic').then(setData).catch(() => {})
  useEffect(() => {
    load()
    const iv = setInterval(load, 15000)
    return () => clearInterval(iv)
  }, [])

  const start = async () => {
    if (!form.name.trim() || !form.birthplace.trim()) { message.warning(t('m.need')); return }
    setStarting(true)
    try {
      const r = await apiPost('/api/mystic/start', form)
      message.success(t('m.started', { seed: r.seed, n: r.count }), 6)
      load()
    } catch (e) { message.error(String(e.message || e)) } finally { setStarting(false) }
  }

  const stop = async () => {
    try {
      await apiPost('/api/mystic/stop', {})
      message.success(t('m.stopped'))
      load()
    } catch (e) { message.error(String(e.message || e)) }
  }

  const alm = data?.almanac
  const plan = data?.plan
  const active = data?.active

  const fieldLabel = (text, hint) => (
    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
      {text}{' '}
      {hint && <Tooltip title={hint}><QuestionCircleOutlined style={{ color: '#888' }} /></Tooltip>}
    </Typography.Text>
  )

  return (
    <Card
      style={{ borderColor: '#642ab5' }}
      title={(
        <Space wrap>
          {t('m.title')}
          <Tag color="purple">{t('m.fun')}</Tag>
          {active && <Tag color="processing">{t('m.active')}</Tag>}
        </Space>
      )}
      extra={alm && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t('m.today', { lunar: alm.lunar, gz: alm.day_ganzhi, jx: alm.jianxing })}
          <Tag color={alm.is_lucky_day ? 'gold' : 'default'} style={{ marginRight: 0 }}>
            {alm.is_lucky_day ? t('m.lucky') : t('m.unlucky')}
          </Tag>
        </Typography.Text>
      )}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Alert
          type="warning" showIcon message={t('m.disclaimer')}
          action={alm && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('m.yi')}:{alm.yi?.join('、')} {t('m.ji')}:{alm.ji?.join('、')}
            </Typography.Text>
          )}
        />
        {lang === 'en' && <Typography.Text type="secondary" style={{ fontSize: 12 }}>ℹ️ {t('m.zh.note')}</Typography.Text>}

        {plan && (
          <>
            <Descriptions size="small" bordered column={{ xs: 1, md: 4 }}
              items={[
                { label: t('m.master'), children: plan.profile?.name },
                { label: t('m.lunarbirth'), children: plan.fate?.lunar_birth },
                { label: t('m.fate'), children: `${plan.fate?.year_ganzhi} ${plan.fate?.element} · ${t('m.animal')}${plan.fate?.animal}` },
                { label: t('m.seed'), children: <Typography.Text code copyable>{plan.seed}</Typography.Text> },
                { label: t('m.day'), children: `${plan.day?.day_ganzhi} · ${plan.day?.jianxing} · ${plan.day?.is_lucky_day ? t('m.lucky') : t('m.unlucky')}` },
                { label: t('m.perusd'), children: `$${plan.usd}` },
                { label: t('m.cap'), children: plan.max_price },
                {
                  label: t('m.tp'),
                  children: plan.tp_mode === 'book'
                    ? `${t('m.tp.book')} @${plan.tp_price}`
                    : t('m.tp.settle'),
                },
                { label: t('m.pnl'), children: <Pnl v={plan.pnl} bold /> },
              ]}
            />
            <Row gutter={16} align="middle">
              <Col flex="auto">
                <Progress
                  percent={Math.round((plan.done / plan.total) * 100)}
                  success={{ percent: Math.round(((plan.filled ?? 0) / plan.total) * 100) }}
                  format={() => t('m.progress', { d: plan.done, f: plan.filled ?? 0, p: plan.placed, t: plan.total })}
                />
              </Col>
              {active && (
                <Col>
                  <Popconfirm title={t('m.stop.confirm')} onConfirm={stop} okText={t('m.stop.ok')} cancelText={t('c.cancel')}>
                    <Button danger>{t('m.stop')}</Button>
                  </Popconfirm>
                </Col>
              )}
            </Row>
            {(plan.entries || []).length > 0 && (
              <Table
                size="small" rowKey="i" pagination={false}
                dataSource={plan.entries}
                scroll={{ y: 380, x: 900 }}
                columns={[
                  { title: '#', dataIndex: 'i', width: 48 },
                  { title: t('c.round'), dataIndex: 'start_ts', width: 105, render: (v) => fmtTs(v, 'MM-DD HH:mm') },
                  { title: t('m.tbl.fate'), dataIndex: 'side', width: 92, render: (s) => <SideTag s={s} /> },
                  {
                    title: t('m.tbl.status'), key: 'st', width: 150,
                    filters: [
                      { text: t('m.f.filled'), value: 'filled' },
                      { text: t('m.f.ordered'), value: 'ordered' },
                      { text: t('m.f.wait'), value: 'wait' },
                      { text: t('m.f.miss'), value: 'miss' },
                    ],
                    onFilter: (v, r) => {
                      if (v === 'filled') return ['tp_set', 'holding', 'settled'].includes(r.pos_state)
                      if (v === 'ordered') return r.pos_state === 'ordered'
                      if (v === 'wait') return !r.pos_state && !r.missed
                      return r.pos_state === 'skipped' || (!r.pos_state && r.missed)
                    },
                    render: (_, r) => {
                      if (r.pos_state === 'settled') return <Tag color="success">{t('m.s.settled')}</Tag>
                      if (r.pos_state === 'tp_set' || r.pos_state === 'holding') return <Tag color="success">{t('m.s.holding')}</Tag>
                      if (r.pos_state === 'ordered') return <Tag color="processing">{t('m.s.ordered')}</Tag>
                      if (r.pos_state === 'skipped') return <Tag>{t('m.s.skipped')}</Tag>
                      if (r.missed) return <Tag>{t('m.s.missed')}</Tag>
                      return <Tag color="default">{t('m.s.wait')}</Tag>
                    },
                  },
                  { title: t('c.entry'), dataIndex: 'entry_price', width: 80, render: (v) => (v != null ? v.toFixed(2) : '—') },
                  { title: t('c.pnl'), dataIndex: 'pnl', width: 85, render: (v) => <Pnl v={v} /> },
                  { title: t('m.tbl.divine'), dataIndex: 'reason', render: (v) => <Typography.Text style={{ fontSize: 12 }}>{v}</Typography.Text> },
                ]}
              />
            )}
          </>
        )}

        {!active && (
          <>
            <Divider plain style={{ margin: '4px 0' }}>{plan ? t('m.restart') : t('m.new')}</Divider>
            <Row gutter={[12, 12]}>
              <Col xs={12} md={4}>
                {fieldLabel(t('m.name'), t('m.name.hint'))}
                <Input placeholder={t('m.name.ph')} value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </Col>
              <Col xs={12} md={4}>
                {fieldLabel(t('m.birth'))}
                <DatePicker
                  style={{ width: '100%' }} placeholder={t('m.birth.ph')}
                  value={form.birth ? dayjs(form.birth) : null}
                  onChange={(d) => setForm({ ...form, birth: d ? d.format('YYYY-MM-DD') : '' })}
                />
              </Col>
              <Col xs={12} md={3}>
                {fieldLabel(t('m.gender'))}
                <Segmented
                  block value={form.gender}
                  options={[{ label: t('m.male'), value: '男' }, { label: t('m.female'), value: '女' }]}
                  onChange={(v) => setForm({ ...form, gender: v })}
                />
              </Col>
              <Col xs={12} md={4}>
                {fieldLabel(t('m.place'))}
                <Input placeholder={t('m.place.ph')} value={form.birthplace}
                  onChange={(e) => setForm({ ...form, birthplace: e.target.value })} />
              </Col>
              <Col xs={12} md={3}>
                {fieldLabel(t('m.count'), t('m.count.hint'))}
                <InputNumber style={{ width: '100%' }} min={1} max={100} precision={0}
                  value={form.count} addonAfter={t('m.count.unit') || null}
                  onChange={(v) => setForm({ ...form, count: v })} />
              </Col>
              <Col xs={12} md={3}>
                {fieldLabel(t('m.usd'))}
                <InputNumber style={{ width: '100%' }} min={0.5} max={100} prefix="$"
                  value={form.usd} addonAfter={t('m.usd.unit')}
                  onChange={(v) => setForm({ ...form, usd: v })} />
              </Col>
              <Col xs={12} md={3}>
                {fieldLabel(t('m.maxp'), t('m.maxp.hint'))}
                <InputNumber style={{ width: '100%' }} min={0.51} max={0.85} step={0.01}
                  value={form.max_price} addonBefore="≤$"
                  onChange={(v) => setForm({ ...form, max_price: v })} />
              </Col>
              <Col xs={12} md={4}>
                {fieldLabel(t('m.tp'), t('m.tp.hint'))}
                <Segmented
                  block value={form.tp_mode}
                  options={[
                    { label: t('m.tp.settle'), value: 'settle' },
                    { label: t('m.tp.book'), value: 'book' },
                  ]}
                  onChange={(v) => setForm({ ...form, tp_mode: v })}
                />
              </Col>
              {form.tp_mode === 'book' && (
                <Col xs={12} md={3}>
                  {fieldLabel(t('m.tp.price'), t('m.tp.price.hint'))}
                  <InputNumber style={{ width: '100%' }} min={0.55} max={0.99} step={0.01}
                    value={form.tp_price} prefix="$"
                    onChange={(v) => setForm({ ...form, tp_price: v })} />
                </Col>
              )}
            </Row>
            <Popconfirm
              title={t('m.start.title')}
              description={t('m.start.desc', {
                n: form.count || 1,
                h: (((form.count || 1) * 5) / 60).toFixed(1),
                c: ((form.usd || 1) * (form.count || 1)).toFixed(0),
              })}
              onConfirm={start} okText={t('m.start.ok')} cancelText={t('m.start.no')}
            >
              <Button type="primary" icon={<ThunderboltOutlined />} loading={starting}
                style={{ background: '#642ab5', borderColor: '#642ab5' }}>
                {t('m.go')}
              </Button>
            </Popconfirm>
          </>
        )}
      </Space>
    </Card>
  )
}
