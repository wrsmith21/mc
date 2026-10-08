import Plotly from 'plotly.js-basic-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'
import { brand } from '../brand'

const PlotComponent = createPlotlyComponent(Plotly)

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function Plot({ data, layout, height = 340 }: { data: any[]; layout?: any; height?: number }) {
  return (
    <PlotComponent
      data={data}
      layout={{
        height,
        margin: { l: 48, r: 12, t: 8, b: 40 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { family: brand.font, size: 12, color: brand.colors.muted },
        xaxis: { gridcolor: '#eff0f2', linecolor: brand.colors.line, zeroline: false },
        yaxis: { gridcolor: '#eff0f2', zeroline: false },
        legend: { orientation: 'h', y: -0.18 },
        hoverlabel: { font: { family: brand.font } },
        ...layout,
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  )
}
