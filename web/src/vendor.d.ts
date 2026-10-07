declare module 'plotly.js-dist-min'
declare module 'react-plotly.js/factory' {
  import type { ComponentType } from 'react'
  const createPlotlyComponent: (plotly: unknown) => ComponentType<Record<string, unknown>>
  export default createPlotlyComponent
}
