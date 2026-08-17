declare module "meta-capi-param-builder-clientjs" {
  export type MetaCapiParameterValues = Record<string, string> & {
    _fbc?: string;
    _fbp?: string;
  };

  export function processAndCollectAllParams(
    url?: string | null,
    getIpFn?: (() => string | Promise<string>) | null,
  ): Promise<MetaCapiParameterValues>;

  export function getFbc(): string;
  export function getFbp(): string;

  const clientParamBuilder: {
    processAndCollectAllParams: typeof processAndCollectAllParams;
    getFbc: typeof getFbc;
    getFbp: typeof getFbp;
  };

  export default clientParamBuilder;
}
