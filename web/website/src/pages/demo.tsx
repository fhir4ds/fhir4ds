import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import BrowserOnly from '@docusaurus/BrowserOnly';
import WasmDemo from '@site/src/components/WasmDemo';

export default function DemoPage(): JSX.Element {
  return (
    <Layout title="Live Demo">
      <main>
        <div className="container" style={{padding: '2rem 0'}}>
          <Heading as="h1" style={{color: '#f1f5f9'}}>
            Live Demo
          </Heading>
          <BrowserOnly>
            {() => <WasmDemo type="playground" />}
          </BrowserOnly>
        </div>
      </main>
    </Layout>
  );
}
