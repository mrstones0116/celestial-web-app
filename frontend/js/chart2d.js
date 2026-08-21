/**
 * 2D赤经-赤纬图表模块
 */
class Chart2D {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.SPECTRAL_COLORS = {
            'O': '#9bb0ff',
            'B': '#aabfff',
            'A': '#cad7ff',
            'F': '#f8f7ff',
            'G': '#fff4ea',
            'K': '#ffd2a1',
            'M': '#ffcc6f',
            'Other': '#aaaaaa'
        };
    }

    draw(stars) {
        const ctx = this.ctx;
        const W = this.canvas.width;
        const H = this.canvas.height;
        const padding = 50;

        // 清空
        ctx.fillStyle = '#111';
        ctx.fillRect(0, 0, W, H);

        // 坐标轴
        ctx.strokeStyle = '#444';
        ctx.lineWidth = 1;

        // 网格线
        ctx.setLineDash([4, 4]);
        for (let ra = 0; ra <= 24; ra += 6) {
            const x = padding + (ra / 24) * (W - 2 * padding);
            ctx.beginPath();
            ctx.moveTo(x, padding);
            ctx.lineTo(x, H - padding);
            ctx.stroke();

            ctx.fillStyle = '#888';
            ctx.font = '11px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(`${ra}h`, x, H - padding + 18);
        }

        for (let dec = -90; dec <= 90; dec += 30) {
            const y = H - padding - ((dec + 90) / 180) * (H - 2 * padding);
            ctx.beginPath();
            ctx.moveTo(padding, y);
            ctx.lineTo(W - padding, y);
            ctx.stroke();

            ctx.fillStyle = '#888';
            ctx.font = '11px Arial';
            ctx.textAlign = 'right';
            ctx.fillText(`${dec}°`, padding - 8, y + 4);
        }
        ctx.setLineDash([]);

        // 轴标签
        ctx.fillStyle = '#aaa';
        ctx.font = '12px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('赤经 (RA)', W / 2, H - 8);

        ctx.save();
        ctx.translate(14, H / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('赤纬 (Dec)', 0, 0);
        ctx.restore();

        // 绘制星星（反转X轴，符合天文惯例）
        stars.forEach(star => {
            const x = W - padding - (star.ra_hours / 24) * (W - 2 * padding);
            const y = H - padding - ((star.dec + 90) / 180) * (H - 2 * padding);
            const size = Math.max(1, 4 - star.mag * 0.5);

            ctx.beginPath();
            ctx.arc(x, y, size, 0, Math.PI * 2);
            ctx.fillStyle = this.SPECTRAL_COLORS[star.spect_class] || '#aaa';
            ctx.fill();
        });

        // 标题
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 13px Arial';
        ctx.textAlign = 'center';
        ctx.fillText(`赤经-赤纬坐标图 (${stars.length} 颗星)`, W / 2, 20);
    }
}