import Plotly from 'plotly.js-dist-min'
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
        margin: { l: 56, r: 16, t: 10, b: 44 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { family: brand.font, size: 14, color: brand.colors.ink },
        xaxis: { gridcolor: '#ebe6e2', zeroline: false },
        yaxis: { gridcolor: '#ebe6e2', zeroline: false },
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
