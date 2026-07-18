import React, { useContext } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { LangCtx, LangProvider } from './i18n'
import App from './App'

function Root() {
  const { lang } = useContext(LangCtx)
  dayjs.locale(lang === 'en' ? 'en' : 'zh-cn')
  return (
    <ConfigProvider
      locale={lang === 'en' ? enUS : zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: { colorPrimary: '#1668dc', borderRadius: 8 },
      }}
    >
      <App />
    </ConfigProvider>
  )
}

createRoot(document.getElementById('root')).render(
  <LangProvider>
    <Root />
  </LangProvider>,
)
